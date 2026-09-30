"""Przeglądarka biblioteki: oś czasu (lata → miesiące) i mapa miejsc (OpenStreetMap).

Działa w oknie programu (dane projektu) i jako osobny serwer tylko do odczytu dla telefonu —
z komputera (sieć domowa / Tailscale, z PIN-em) albo 24/7 z Raspberry Pi:
    python -m katalogator galeria --folder /mnt/mycloud/Biblioteka --pin 1234
"""

from __future__ import annotations

import io
import json
import os
import re
import secrets
import socket
import threading
import time
from collections import OrderedDict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import analiza, miejsca, skaner

UI = Path(__file__).parent / "ui"
_TYPY = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".png": "image/png",
         ".ico": "image/x-icon", ".html": "text/html; charset=utf-8", ".svg": "image/svg+xml",
         ".webp": "image/webp", ".jpg": "image/jpeg"}


def plik_ui(sciezka_url: str) -> tuple[bytes, str] | None:
    """Plik interfejsu spod /ui/… (także podfoldery, np. /ui/mapa/leaflet.js) — nigdy spoza katalogu ui."""
    wzgl = sciezka_url[len("/ui/"):] if sciezka_url.startswith("/ui/") else ""
    p = (UI / wzgl).resolve()
    if not wzgl or UI.resolve() not in p.parents or p.suffix not in _TYPY or not p.is_file():
        return None
    return p.read_bytes(), _TYPY[p.suffix]


# Ulubione, albumy i miniatury filmów — w bazie oglądanej galerii (projektu albo Przeglądarki); klucz = ścieżka pliku
SCHEMAT_KOLEKCJI = """
CREATE TABLE IF NOT EXISTS g_ulubione (sciezka TEXT PRIMARY KEY, czas REAL NOT NULL);
CREATE TABLE IF NOT EXISTS g_albumy (id INTEGER PRIMARY KEY AUTOINCREMENT, nazwa TEXT NOT NULL, czas REAL NOT NULL);
CREATE TABLE IF NOT EXISTS g_album_pliki (album INTEGER NOT NULL, sciezka TEXT NOT NULL, czas REAL NOT NULL,
                                          PRIMARY KEY (album, sciezka));
CREATE TABLE IF NOT EXISTS g_min_filmow (sciezka TEXT PRIMARY KEY, mtime REAL NOT NULL, dane BLOB NOT NULL);
"""
_MIESIACE_SZUKANIA = [("stycz", 1), ("lut", 2), ("mar", 3), ("kwie", 4), ("maj", 5), ("czerw", 6), ("lip", 7),
                      ("sierp", 8), ("wrze", 9), ("paźdz", 10), ("pazdz", 10), ("listop", 11), ("grud", 12)]
_NAZWY_MIES = ["styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec", "sierpień", "wrzesień",
               "październik", "listopad", "grudzień"]
_KOLUMNY = "rowid id, wzgledna, rodzaj, data, lat, lon, rozmiar"


def _nazwa(r: dict) -> dict:
    r["nazwa"] = re.split(r"[\\/]", r.pop("wzgledna"))[-1]
    return r


class Galeria:
    """Dane dla osi czasu i mapy z bazy skanu. korzenie() -> lista folderów (None = wszystko w bazie)."""

    def __init__(self, baza, korzenie=None, pamiec_min: Path | None = None, tylko_zdjecia_ludzi: bool = False):
        self.baza = baza
        # Przeglądarka całych dysków: pomijamy drobne obrazki bez daty z aparatu/nazwy (ikony, grafiki programów)
        self.filtr = (" AND (zrodlo_daty IN ('exif','film','nazwa') OR rozmiar >= 150000 OR rodzaj = 'film')"
                      if tylko_zdjecia_ludzi else "")
        self.korzenie = korzenie or (lambda: None)
        self.pamiec_min = pamiec_min  # katalog na miniatury (serwer 24/7) — w oknie tylko pamięć RAM
        self._min: OrderedDict = OrderedDict()
        self._blokada = threading.Lock()

    def _db(self):
        db = skaner.otworz_baze(self.baza)
        if not getattr(self, "_schemat", False):
            db.executescript(SCHEMAT_KOLEKCJI)
            for t in ("g_ulubione", "g_album_pliki"):  # od 1.9.3: nazwa|rozmiar|data — odnajdywanie po przeniesieniu
                if "klucz" not in {r[1] for r in db.execute(f"PRAGMA table_info({t})")}:
                    db.execute(f"ALTER TABLE {t} ADD COLUMN klucz TEXT")
            db.commit()
            self._schemat = True
        return db

    @staticmethod
    def _klucz_sql() -> str:  # nazwa pliku (małe litery) | rozmiar | data zdjęcia
        return ("lower(replace(wzgledna, rtrim(wzgledna, replace(replace(wzgledna, '\\', '/'), '/', '')), '')) "
                "|| '|' || rozmiar || '|' || coalesce(data, '')")

    def _napraw_kolekcje(self, db) -> int:
        """Zdjęcia z ulubionych/albumów przeniesione (Katalogator, Odłożone, ręcznie) — odnajdujemy je po nazwie,
        rozmiarze i dacie i poprawiamy ścieżkę. Zwraca liczbę naprawionych."""
        k = self._klucz_sql()
        brak = {t: db.execute(f"SELECT rowid, sciezka, klucz FROM {t} WHERE klucz IS NOT NULL AND sciezka NOT IN "
                              f"(SELECT sciezka FROM pliki)").fetchall() for t in ("g_ulubione", "g_album_pliki")}
        if not any(brak.values()):
            return 0
        potrzebne = {r["klucz"] for w in brak.values() for r in w}
        gdzie: dict[str, str] = {}
        for r in db.execute(f"SELECT sciezka, {k} klucz FROM pliki WHERE rodzaj IN ('zdjecie','film')"):
            if r["klucz"] in potrzebne and r["klucz"] not in gdzie:
                gdzie[r["klucz"]] = r["sciezka"]
        n = 0
        for t, wiersze in brak.items():
            for r in wiersze:
                nowa = gdzie.get(r["klucz"])
                if nowa:
                    db.execute(f"UPDATE OR IGNORE {t} SET sciezka=? WHERE rowid=?", (nowa, r["rowid"]))
                    n += 1
        db.commit()
        return n

    def _warunek(self, obszar: tuple | None = None) -> tuple[str, list]:
        w, arg = self._zakres()
        if obszar:  # prostokąt z mapy: (lat1, lat2, lon1, lon2)
            w += " AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?"
            arg = arg + [min(obszar[:2]), max(obszar[:2]), min(obszar[2:]), max(obszar[2:])]
        return w, arg

    def _zakres(self) -> tuple[str, list]:
        k = self.korzenie()
        if k is None:  # wszystko w bazie
            return self.filtr, []
        if not k:  # zakres pusty (np. biblioteka, gdy nie wybrano miejsca docelowego)
            return " AND 0", []
        czesci, arg = [], []
        for r in k:
            r = os.path.abspath(r)
            pref = r.rstrip("\\/") + os.sep
            czesci.append("(korzen = ? OR substr(sciezka, 1, ?) = ?)")
            arg += [r, len(pref), pref]
        return " AND (" + " OR ".join(czesci) + ")" + self.filtr, arg

    def lata(self, obszar: tuple | None = None) -> dict:
        w, arg = self._warunek(obszar)
        db = self._db()
        try:
            lata: dict[str, dict] = {}
            for r in db.execute(
                    f"""SELECT substr(data, 1, 4) rok, CAST(substr(data, 6, 2) AS INTEGER) mies, COUNT(*) n,
                               SUM(lat IS NOT NULL) gps FROM pliki
                        WHERE rodzaj IN ('zdjecie', 'film') AND data IS NOT NULL {w}
                        GROUP BY rok, mies ORDER BY rok DESC, mies DESC""", arg):
                rok = lata.setdefault(r["rok"], {"rok": r["rok"], "n": 0, "gps": 0, "miesiace": []})
                rok["n"] += r["n"]
                rok["gps"] += r["gps"] or 0
                rok["miesiace"].append({"m": r["mies"], "n": r["n"]})
            bez = db.execute(f"SELECT COUNT(*) FROM pliki WHERE rodzaj IN ('zdjecie','film') AND data IS NULL {w}",
                             arg).fetchone()[0]
        finally:
            db.close()
        l = list(lata.values())
        return {"lata": l, "razem": sum(x["n"] for x in l) + bez, "z_gps": sum(x["gps"] for x in l),
                "bez_daty": bez}

    def pliki(self, rok: str, miesiac: int | None, od: int = 0, ile: int = 200, obszar: tuple | None = None) -> dict:
        w, arg = self._warunek(obszar)
        filtr = "substr(data, 1, 4) = ?" + (" AND CAST(substr(data, 6, 2) AS INTEGER) = ?" if miesiac else "")
        a = [str(rok)] + ([int(miesiac)] if miesiac else [])
        db = self._db()
        try:
            razem = db.execute(f"SELECT COUNT(*) FROM pliki WHERE rodzaj IN ('zdjecie','film') AND {filtr} {w}",
                               a + arg).fetchone()[0]
            wiersze = [dict(r) for r in db.execute(
                f"""SELECT rowid id, wzgledna, rodzaj, data, lat, lon, rozmiar FROM pliki
                    WHERE rodzaj IN ('zdjecie','film') AND {filtr} {w} ORDER BY data, wzgledna LIMIT ? OFFSET ?""",
                a + arg + [int(ile), int(od)])]
        finally:
            db.close()
        for r in wiersze:
            r["nazwa"] = re.split(r"[\\/]", r.pop("wzgledna"))[-1]
        return {"razem": razem, "pliki": wiersze}

    def mapa(self) -> dict:
        """Wszystkie zdjęcia i filmy z GPS — zwięźle: [id, lat, lon, 1 = film]."""
        w, arg = self._warunek()
        db = self._db()
        try:
            punkty = [[r[0], round(r[1], 5), round(r[2], 5), 1 if r[3] == "film" else 0] for r in db.execute(
                f"""SELECT rowid, lat, lon, rodzaj FROM pliki
                    WHERE rodzaj IN ('zdjecie','film') AND lat IS NOT NULL AND lon IS NOT NULL {w}""", arg)]
        finally:
            db.close()
        return {"punkty": punkty}

    def _wiersz(self, id_: int):
        w, arg = self._warunek()
        db = self._db()
        try:
            return db.execute(f"SELECT rowid id, * FROM pliki WHERE rowid = ? {w}", [int(id_)] + arg).fetchone()
        finally:
            db.close()

    def plik(self, id_: int) -> dict | None:
        r = self._wiersz(id_)
        if not r:
            return None
        miejsce = None
        if r["lat"] is not None:
            try:
                e = miejsca.etykieta(r["lat"], r["lon"])
                miejsce = e if not e.startswith("@") else miejsca.fraza(e)
            except Exception:
                miejsce = None
        db = self._db()
        try:
            ulub = db.execute("SELECT 1 FROM g_ulubione WHERE sciezka=?", (r["sciezka"],)).fetchone() is not None
            albumy = [x[0] for x in db.execute("SELECT album FROM g_album_pliki WHERE sciezka=?", (r["sciezka"],))]
        finally:
            db.close()
        return {"id": r["id"], "nazwa": re.split(r"[\\/]", r["wzgledna"])[-1], "folder": os.path.dirname(r["wzgledna"]),
                "data": r["data"], "rodzaj": r["rodzaj"], "aparat": r["aparat"], "lat": r["lat"], "lon": r["lon"],
                "miejsce": miejsce, "rozmiar": r["rozmiar"], "ulubione": ulub, "albumy": albumy}

    def sciezka(self, id_: int, rodzaj: str | None = None) -> str | None:
        r = self._wiersz(id_)
        if not r or (rodzaj and r["rodzaj"] != rodzaj):
            return None
        return r["sciezka"]

    def miniatura(self, id_: int, srednia: bool = False) -> bytes | None:
        film = self.sciezka(id_, "film")
        if film:  # klatka zapisana przez okno programu (przeglądarka wyciąga ją z filmu)
            db = self._db()
            try:
                r = db.execute("SELECT mtime, dane FROM g_min_filmow WHERE sciezka=?", (film,)).fetchone()
            finally:
                db.close()
            try:
                return r["dane"] if r and abs(r["mtime"] - os.path.getmtime(film)) < 1 else None
            except OSError:
                return None
        klucz = (int(id_), srednia)
        with self._blokada:
            if klucz in self._min:
                self._min.move_to_end(klucz)
                return self._min[klucz]
        sc = self.sciezka(id_, "zdjecie")
        if not sc:
            return None
        plik_cache = None
        if self.pamiec_min and not srednia:  # na dysku tylko małe miniatury siatki (średnie są duże)
            try:
                st = os.stat(sc)  # w nazwie data i rozmiar pliku — zmieniony plik = nowa miniatura
                plik_cache = self.pamiec_min / f"{id_ % 100:02d}" / f"{id_}-{int(st.st_mtime)}-{st.st_size}.jpg"
            except OSError:
                return None
        dane = None
        if plik_cache and plik_cache.exists():
            dane = plik_cache.read_bytes()
        if dane is None:
            try:
                if srednia:
                    im, _ = analiza.miniatura(sc, min_bok=200)
                    im.thumbnail((600, 600))
                else:
                    im, _ = analiza.miniatura(sc, min_bok=150)
                    im.thumbnail((260, 260))
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=82)
                dane = buf.getvalue()
            except Exception:
                return None
            if plik_cache:
                try:
                    plik_cache.parent.mkdir(parents=True, exist_ok=True)
                    plik_cache.write_bytes(dane)
                    self._zapisanych = getattr(self, "_zapisanych", 0) + 1
                    if self._zapisanych % 500 == 0:
                        threading.Thread(target=self._przytnij_pamiec, daemon=True).start()
                except OSError:
                    pass
        with self._blokada:
            self._min[klucz] = dane
            while len(self._min) > 800:
                self._min.popitem(last=False)
        return dane

    # --- wyszukiwarka: miejsce, rok, miesiąc, nazwa pliku/folderu, aparat ---------------------------------
    def szukaj(self, tekst: str, od: int = 0, ile: int = 200) -> dict:
        slowa = [s for s in re.split(r"[\s,;]+", (tekst or "").strip()) if s]
        rok, mies, reszta = None, None, []
        for s in slowa:
            sl = s.lower()
            m = re.fullmatch(r"(19\d\d|20\d\d)(?:[-./](\d{1,2}))?", sl) or re.fullmatch(r"(\d{1,2})[-./](19\d\d|20\d\d)", sl)
            if m and rok is None:
                a, b = m.groups()
                rok, mm = (a, b) if len(a) == 4 else (b, a)
                if mm and 1 <= int(mm) <= 12:
                    mies = int(mm)
                continue
            mm = next((n for p, n in _MIESIACE_SZUKANIA if len(sl) >= 3 and (sl.startswith(p) or p.startswith(sl))), None)
            if mm and mies is None and not sl.isdigit():
                mies = mm
                continue
            reszta.append(s)
        miejsce, tekstowe = None, reszta
        if reszta:
            miejsce = miejsca.szukaj_miejsca(" ".join(reszta))
            if miejsce:
                tekstowe = []
            else:
                for i, s in enumerate(reszta):
                    miejsce = miejsca.szukaj_miejsca(s)
                    if miejsce:
                        tekstowe = reszta[:i] + reszta[i + 1:]
                        break
        if not (rok or mies or miejsce or tekstowe):
            return {"razem": 0, "pliki": [], "opis": ""}
        w, arg = self._warunek()
        war, a = [], []
        if rok:
            war.append("substr(data, 1, 4) = ?"); a.append(rok)
        if mies:
            war.append("CAST(substr(data, 6, 2) AS INTEGER) = ?"); a.append(mies)
        for s in tekstowe:
            war.append("(lower(wzgledna) LIKE ? OR lower(coalesce(aparat, '')) LIKE ?)")
            a += [f"%{s.lower()}%"] * 2
        if miejsce:
            if miejsce["pl"]:
                war.append("(" + " OR ".join(["(lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?)"] * len(miejsce["pl"])) + ")")
                for la, lo, _ in miejsce["pl"]:
                    a += [la - 0.3, la + 0.3, lo - 0.5, lo + 0.5]
            else:
                war.append("lat IS NOT NULL")
        sql = (f"FROM pliki WHERE rodzaj IN ('zdjecie','film') {w} AND " + " AND ".join(war))
        db = self._db()
        try:
            if miejsce:  # dokładnie: najbliższa miejscowość / kraj zdjęcia (jak w nazwach folderów)
                wiersze = [dict(r) for r in db.execute(f"SELECT {_KOLUMNY} {sql} ORDER BY data DESC", arg + a)]
                cel = miejsce["nazwa"] if miejsce["pl"] else "@" + miejsce["kraj"]

                def pasuje(r):
                    e = miejsca.etykieta(r["lat"], r["lon"])
                    return e == cel or (miejsce["kraj"] == "PL" and not e.startswith("@"))
                wiersze = [r for r in wiersze if pasuje(r)]
                razem, wiersze = len(wiersze), wiersze[od:od + ile]
            else:
                razem = db.execute(f"SELECT COUNT(*) {sql}", arg + a).fetchone()[0]
                wiersze = [dict(r) for r in db.execute(f"SELECT {_KOLUMNY} {sql} ORDER BY data DESC LIMIT ? OFFSET ?",
                                                       arg + a + [int(ile), int(od)])]
        finally:
            db.close()
        opis = [miejsce["nazwa"]] if miejsce else []
        if mies:
            opis.append(_NAZWY_MIES[mies - 1] + (f" {rok}" if rok else ""))
        elif rok:
            opis.append(rok)
        opis += [f"„{s}”" for s in tekstowe]
        return {"razem": razem, "pliki": [_nazwa(r) for r in wiersze], "opis": " · ".join(opis)}

    # --- ten dzień lata temu ------------------------------------------------------------------------------
    def tego_dnia(self, md: str | None = None) -> dict:
        md = md if md and re.fullmatch(r"\d\d-\d\d", md) else time.strftime("%m-%d")
        w, arg = self._warunek()
        db = self._db()
        try:
            wiersze = [dict(r) for r in db.execute(
                f"""SELECT {_KOLUMNY} FROM pliki WHERE rodzaj IN ('zdjecie','film') AND substr(data, 6, 5) = ?
                    AND substr(data, 1, 4) < ? {w} ORDER BY data DESC LIMIT 500""", [md, time.strftime("%Y")] + arg)]
        finally:
            db.close()
        lata: dict[str, int] = {}
        for r in wiersze:
            lata[r["data"][:4]] = lata.get(r["data"][:4], 0) + 1
        return {"md": md, "razem": len(wiersze), "lata": [{"rok": k, "n": v} for k, v in lata.items()],
                "pliki": [_nazwa(r) for r in wiersze]}

    # --- ulubione i albumy ----------------------------------------------------------------------------
    def _sciezki(self, db, ids, z_kluczem: bool = False) -> list:
        w, arg = self._warunek()
        wynik = []
        for i in ids[:5000]:
            r = db.execute(f"SELECT sciezka, {self._klucz_sql()} klucz FROM pliki WHERE rowid=? {w}",
                           [int(i)] + arg).fetchone()
            if r:
                wynik.append((r[0], r[1]) if z_kluczem else r[0])
        return wynik

    def ulubione(self, id_: int, wlacz: bool | None = None) -> dict:
        db = self._db()
        try:
            s = self._sciezki(db, [id_], z_kluczem=True)
            if not s:
                return {"blad": "nie ma takiego pliku"}
            (sc, klucz), = s
            jest = db.execute("SELECT 1 FROM g_ulubione WHERE sciezka=?", (sc,)).fetchone() is not None
            nowe = (not jest) if wlacz is None else bool(wlacz)
            if nowe:
                db.execute("INSERT OR IGNORE INTO g_ulubione(sciezka, czas, klucz) VALUES (?,?,?)", (sc, time.time(), klucz))
            else:
                db.execute("DELETE FROM g_ulubione WHERE sciezka=?", (sc,))
            db.commit()
            return {"ulubione": nowe}
        finally:
            db.close()

    def albumy(self) -> dict:
        w, arg = self._warunek()
        db = self._db()
        try:
            self._napraw_kolekcje(db)
            wynik = []
            for a in db.execute("SELECT id, nazwa FROM g_albumy ORDER BY czas DESC").fetchall():
                r = db.execute(f"""SELECT COUNT(*) n, MIN(rowid) okladka FROM pliki WHERE rodzaj IN ('zdjecie','film')
                                   AND sciezka IN (SELECT sciezka FROM g_album_pliki WHERE album=?) {w}""",
                               [a["id"]] + arg).fetchone()
                wynik.append({"id": a["id"], "nazwa": a["nazwa"], "n": r["n"], "okladka": r["okladka"]})
            u = db.execute(f"""SELECT COUNT(*) n, MIN(rowid) okladka FROM pliki WHERE rodzaj IN ('zdjecie','film')
                               AND sciezka IN (SELECT sciezka FROM g_ulubione) {w}""", arg).fetchone()
        finally:
            db.close()
        return {"albumy": wynik, "ulubione": {"n": u["n"], "okladka": u["okladka"]}}

    def album_nowy(self, nazwa: str, ids=()) -> dict:
        nazwa = " ".join(str(nazwa or "").split())[:80] or "Nowy album"
        db = self._db()
        try:
            a = db.execute("INSERT INTO g_albumy(nazwa, czas) VALUES (?,?)", (nazwa, time.time())).lastrowid
            db.commit()
        finally:
            db.close()
        return {"id": a, "nazwa": nazwa, **self.album_dodaj(a, ids)}

    def album_dodaj(self, album: int, ids) -> dict:
        db = self._db()
        try:
            if not db.execute("SELECT 1 FROM g_albumy WHERE id=?", (int(album),)).fetchone():
                return {"blad": "nie ma takiego albumu"}
            s = self._sciezki(db, list(ids or []), z_kluczem=True)
            db.executemany("INSERT OR IGNORE INTO g_album_pliki(album, sciezka, czas, klucz) VALUES (?,?,?,?)",
                           [(int(album), x, time.time(), k) for x, k in s])
            db.commit()
            return {"dodane": len(s)}
        finally:
            db.close()

    def album_usun_pliki(self, album: int, ids) -> dict:
        db = self._db()
        try:
            s = self._sciezki(db, list(ids or []))
            db.executemany("DELETE FROM g_album_pliki WHERE album=? AND sciezka=?", [(int(album), x) for x in s])
            db.commit()
            return {"usuniete": len(s)}
        finally:
            db.close()

    def album_usun(self, album: int) -> dict:  # tylko album — zdjęcia zostają na dysku
        db = self._db()
        try:
            db.execute("DELETE FROM g_album_pliki WHERE album=?", (int(album),))
            db.execute("DELETE FROM g_albumy WHERE id=?", (int(album),))
            db.commit()
            return {"ok": True}
        finally:
            db.close()

    def album_nazwa(self, album: int, nazwa: str) -> dict:
        nazwa = " ".join(str(nazwa or "").split())[:80]
        if not nazwa:
            return {"blad": "Podaj nazwę."}
        db = self._db()
        try:
            db.execute("UPDATE g_albumy SET nazwa=? WHERE id=?", (nazwa, int(album)))
            db.commit()
            return {"ok": True, "nazwa": nazwa}
        finally:
            db.close()

    def kolekcja(self, typ: str, album: int = 0, od: int = 0, ile: int = 200) -> dict:
        w, arg = self._warunek()
        if typ == "ulubione":
            pod, a, nazwa = "SELECT sciezka FROM g_ulubione", [], "⭐ Ulubione"
        else:
            pod, a = "SELECT sciezka FROM g_album_pliki WHERE album=?", [int(album)]
        db = self._db()
        try:
            if typ != "ulubione":
                r = db.execute("SELECT nazwa FROM g_albumy WHERE id=?", (int(album),)).fetchone()
                if not r:
                    return {"blad": "nie ma takiego albumu"}
                nazwa = r[0]
            self._napraw_kolekcje(db)
            sql = f"FROM pliki WHERE rodzaj IN ('zdjecie','film') AND sciezka IN ({pod}) {w}"
            razem = db.execute(f"SELECT COUNT(*) {sql}", a + arg).fetchone()[0]
            wiersze = [dict(r) for r in db.execute(f"SELECT {_KOLUMNY} {sql} ORDER BY data, wzgledna LIMIT ? OFFSET ?",
                                                   a + arg + [int(ile), int(od)])]
        finally:
            db.close()
        return {"razem": razem, "pliki": [_nazwa(r) for r in wiersze], "nazwa": nazwa}

    # --- filmy: miniatura wyciągnięta przez okno programu, odtwarzacz systemowy ---------------------------
    def zapisz_miniature_filmu(self, id_: int, jpeg: bytes) -> dict:
        film = self.sciezka(id_, "film")
        if not film or not jpeg.startswith(b"\xff\xd8") or len(jpeg) > 400_000:
            return {"blad": "zła miniatura"}
        try:
            mt = os.path.getmtime(film)
        except OSError:
            return {"blad": "nie ma pliku"}
        db = self._db()
        try:
            db.execute("INSERT OR REPLACE INTO g_min_filmow VALUES (?,?,?)", (film, mt, jpeg))
            db.commit()
        finally:
            db.close()
        return {"ok": True}

    def otworz(self, id_: int) -> dict:
        sc = self.sciezka(id_, "film") or self.sciezka(id_, "zdjecie")  # tylko zdjęcia i filmy — nigdy programy
        if not sc or not os.path.isfile(sc):
            return {"blad": "nie ma pliku"}
        try:
            if os.name == "nt":
                os.startfile(sc)  # noqa: S606 — domyślny program Windows (np. Filmy i TV, VLC)
            else:
                import subprocess
                subprocess.Popen(["xdg-open", sc], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            return {"blad": str(e)}
        return {"ok": True}

    MAKS_PAMIEC_MIN = 1_500_000_000  # ~1,5 GB miniatur na dysku; potem usuwamy najdawniej używane

    def _przytnij_pamiec(self) -> None:
        try:
            pliki = [(p.stat().st_atime, p.stat().st_size, p) for p in Path(self.pamiec_min).rglob("*.jpg")]
        except OSError:
            return
        razem = sum(r for _, r, _ in pliki)
        if razem <= self.MAKS_PAMIEC_MIN:
            return
        for _, r, p in sorted(pliki):
            try:
                p.unlink()
            except OSError:
                continue
            razem -= r
            if razem <= self.MAKS_PAMIEC_MIN * 0.8:
                break

    def podglad(self, id_: int) -> bytes | None:
        sc = self.sciezka(id_, "zdjecie")
        if not sc:
            return None
        try:
            im = analiza._obraz_do_tekstu(sc, bok=1800)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=86)
            return buf.getvalue()
        except Exception:
            return None


def wyslij_strumien(h: BaseHTTPRequestHandler, sciezka: str | None) -> None:
    """Film z obsługą zakresów (Range) — przeglądarka czyta tylko potrzebny fragment."""
    if not sciezka or not os.path.isfile(sciezka):
        h.send_response(HTTPStatus.NOT_FOUND)
        h.send_header("Content-Length", "0")
        h.end_headers()
        return
    rozm = os.path.getsize(sciezka)
    typ = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/mp4", ".3gp": "video/3gpp",
           ".webm": "video/webm", ".mkv": "video/webm"}.get(Path(sciezka).suffix.lower(), "application/octet-stream")
    start, koniec = 0, rozm - 1
    m = re.match(r"bytes=(\d*)-(\d*)", h.headers.get("Range", ""))
    if m and (m.group(1) or m.group(2)):
        if m.group(1):
            start = int(m.group(1))
            koniec = min(int(m.group(2)) if m.group(2) else rozm - 1, rozm - 1)
        else:
            start = max(0, rozm - int(m.group(2)))
        if start > koniec:
            h.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            h.send_header("Content-Range", f"bytes */{rozm}")
            h.end_headers()
            return
        h.send_response(HTTPStatus.PARTIAL_CONTENT)
        h.send_header("Content-Range", f"bytes {start}-{koniec}/{rozm}")
    else:
        h.send_response(HTTPStatus.OK)
    h.send_header("Content-Type", typ)
    h.send_header("Accept-Ranges", "bytes")
    h.send_header("Content-Length", str(koniec - start + 1))
    h.end_headers()
    try:
        with open(sciezka, "rb") as f:
            f.seek(start)
            zostalo = koniec - start + 1
            while zostalo > 0:
                k = f.read(min(1 << 20, zostalo))
                if not k:
                    break
                h.wfile.write(k)
                zostalo -= len(k)
    except (ConnectionError, OSError):
        pass  # przeglądarka przerwała pobieranie (np. przewinięcie) — to normalne


def obsluz_api(g: Galeria, sciezka: str, q: dict):
    """/api/g/… -> (treść, typ) albo („film”, ścieżka) albo None, gdy to nie ścieżka galerii."""
    def i(k, d=0):
        try:
            return int(q.get(k, [d])[0])
        except (TypeError, ValueError):
            return d
    def obszar():
        try:
            o = tuple(float(q[k][0]) for k in ("lat1", "lat2", "lon1", "lon2"))
            return o if all(abs(x) <= 360 for x in o) else None
        except (KeyError, ValueError, IndexError):
            return None
    if sciezka == "/api/g/lata":
        return g.lata(obszar()), None
    if sciezka == "/api/g/pliki":
        return g.pliki(q.get("rok", [""])[0], i("miesiac") or None, i("od"), min(i("ile", 200), 500), obszar()), None
    if sciezka == "/api/g/szukaj":
        return g.szukaj(q.get("q", [""])[0][:200], i("od"), min(i("ile", 200), 500)), None
    if sciezka == "/api/g/tego-dnia":
        return g.tego_dnia(q.get("md", [""])[0]), None
    if sciezka == "/api/g/albumy":
        return g.albumy(), None
    if sciezka == "/api/g/kolekcja":
        return g.kolekcja(q.get("typ", [""])[0], i("album"), i("od"), min(i("ile", 200), 500)), None
    if sciezka == "/api/g/mapa":
        return g.mapa(), None
    if sciezka == "/api/g/plik":
        return g.plik(i("id")) or {"blad": "nie ma takiego pliku"}, None
    if sciezka == "/api/g/miniatura":
        return g.miniatura(i("id"), bool(q.get("srednia"))), "image/jpeg"
    if sciezka == "/api/g/podglad":
        return g.podglad(i("id")), "image/jpeg"
    if sciezka == "/api/g/film":
        return "film", g.sciezka(i("id"), "film")
    return None


def obsluz_post(g: Galeria, sciezka: str, dane: dict) -> dict | None:
    """Zmiany kolekcji (ulubione, albumy) i miniatury filmów — tylko z okna programu (telefon jest tylko do odczytu)."""
    ids = [int(x) for x in (dane.get("ids") or []) if str(x).lstrip("-").isdigit()]
    if sciezka == "/api/g/ulubione":
        return g.ulubione(int(dane.get("id") or 0), dane.get("wlacz"))
    if sciezka == "/api/g/album/nowy":
        return g.album_nowy(str(dane.get("nazwa", "")), ids)
    if sciezka == "/api/g/album/dodaj":
        return g.album_dodaj(int(dane.get("album") or 0), ids)
    if sciezka == "/api/g/album/usun-pliki":
        return g.album_usun_pliki(int(dane.get("album") or 0), ids)
    if sciezka == "/api/g/album/usun":
        return g.album_usun(int(dane.get("album") or 0))
    if sciezka == "/api/g/album/nazwa":
        return g.album_nazwa(int(dane.get("album") or 0), str(dane.get("nazwa", "")))
    if sciezka == "/api/g/miniatura-filmu":
        import base64
        try:
            jpeg = base64.b64decode(str(dane.get("jpg", "")).split(",")[-1], validate=True)
        except ValueError:
            return {"blad": "zła miniatura"}
        return g.zapisz_miniature_filmu(int(dane.get("id") or 0), jpeg)
    if sciezka == "/api/g/otworz":
        return g.otworz(int(dane.get("id") or 0))
    return None


# --- serwer dla telefonu (tylko odczyt, PIN) ------------------------------------------------------

def adresy_ip() -> list[str]:
    """Adresy tego komputera w sieci domowej i w Tailscale (100.x) — do wpisania w telefonie."""
    wynik = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in wynik:
                wynik.append(ip)
    except OSError:
        pass
    try:  # adres „wychodzący” (bez wysyłania czegokolwiek)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.0.1", 9))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127.") and ip not in wynik:
            wynik.insert(0, ip)
    except OSError:
        pass
    return sorted(wynik, key=lambda a: (not a.startswith(("192.168.", "10.", "172.")), not a.startswith("100.")))


def losowy_pin() -> str:
    return f"{secrets.randbelow(10**6):06d}"


class SerwerGalerii:
    """HTTP na wszystkich interfejsach; dostęp po PIN-ie (token w przeglądarce telefonu). Galeria tylko do odczytu;
    z `pilot` (program na komputerze) telefon widzi też stan pracy i może uruchamiać kolejne kroki."""

    ZAKRESY = ("biblioteka", "wszystko", "przegladarka")

    def __init__(self, galeria: Galeria, port: int = 8765, pin: str | None = None, host: str = "0.0.0.0",
                 pilot=None, galerie=None, staly_token: str | None = None):
        self.galeria = galeria
        self.pilot = pilot        # pilot.Pilot — stan i sterowanie programem
        self.galerie = galerie    # zakres -> Galeria (telefon wybiera: biblioteka / wszystko / przeglądarka)
        self.pin = pin or losowy_pin()
        self.tokeny: set[str] = set()
        self.staly_token = staly_token  # przy własnym PIN-ie: telefon zostaje zalogowany po restarcie programu
        self.nieudane: dict[str, list[float]] = {}
        self.serwer = ThreadingHTTPServer((host, port), self._handler())
        self.serwer.daemon_threads = True
        self.port = self.serwer.server_address[1]
        self.watek: threading.Thread | None = None

    def start(self) -> "SerwerGalerii":
        self.watek = threading.Thread(target=self.serwer.serve_forever, daemon=True)
        self.watek.start()
        return self

    def stop(self) -> None:
        self.serwer.shutdown()
        self.serwer.server_close()

    def adresy(self) -> list[str]:
        return [f"http://{ip}:{self.port}/" for ip in adresy_ip()]

    def _handler(self):
        s = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _wyslij(self, tresc, typ="application/json; charset=utf-8", kod=HTTPStatus.OK):
                if tresc is None:
                    tresc, typ, kod = b"", "text/plain", HTTPStatus.NOT_FOUND
                dane = (json.dumps(tresc, ensure_ascii=False).encode() if not isinstance(tresc, (bytes, str))
                        else tresc.encode() if isinstance(tresc, str) else tresc)
                self.send_response(kod)
                self.send_header("Content-Type", typ)
                self.send_header("Content-Length", str(len(dane)))
                self.send_header("Cache-Control", "no-store" if typ.startswith("application/json") else "max-age=3600")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(dane)

            def _ok(self, q) -> bool:
                t = self.headers.get("X-Token") or q.get("t", [""])[0]
                return bool(t) and (t in s.tokeny or bool(s.staly_token) and secrets.compare_digest(t, s.staly_token))

            def do_GET(self):
                u = urlparse(self.path)
                q = parse_qs(u.query)
                if u.path == "/" and s.pilot is not None:
                    return self._wyslij((UI / "pilot.html").read_bytes(), "text/html; charset=utf-8")
                if u.path in ("/", "/galeria"):
                    return self._wyslij((UI / "galeria.html").read_bytes(), "text/html; charset=utf-8")
                if u.path.startswith("/ui/"):
                    p = plik_ui(u.path)
                    return self._wyslij(*p) if p else self._wyslij(None)
                if not self._ok(q):
                    return self._wyslij({"blad": "Podaj PIN"}, kod=HTTPStatus.UNAUTHORIZED)
                if u.path == "/api/pilot":
                    return self._wyslij(s.pilot.status() if s.pilot else None)
                g = s.galeria
                z = q.get("z", [""])[0]
                if s.galerie is not None and z in s.ZAKRESY:
                    g = s.galerie(z)
                try:
                    w = obsluz_api(g, u.path, q)
                except Exception as e:  # pragma: no cover - nie wywracamy serwera
                    return self._wyslij({"blad": str(e)}, kod=HTTPStatus.INTERNAL_SERVER_ERROR)
                if w is None:
                    return self._wyslij(None)
                if w[0] == "film":
                    return wyslij_strumien(self, w[1])
                return self._wyslij(w[0], w[1]) if w[1] else self._wyslij(w[0])

            def do_POST(self):
                u = urlparse(self.path)
                if u.path.startswith("/api/pilot/") and s.pilot is not None:
                    if not self._ok(parse_qs(u.query)):
                        return self._wyslij({"blad": "Podaj PIN"}, kod=HTTPStatus.UNAUTHORIZED)
                    try:
                        n = int(self.headers.get("Content-Length") or 0)
                        dane = json.loads(self.rfile.read(min(n, 10000)) or b"{}")
                        dane = dane if isinstance(dane, dict) else {}
                    except ValueError:
                        dane = {}
                    try:
                        blad = s.pilot.akcja(u.path.rsplit("/", 1)[1], dane)
                    except Exception as e:  # pragma: no cover - nie wywracamy serwera
                        blad = str(e)
                    if blad:
                        return self._wyslij({"blad": blad}, kod=HTTPStatus.BAD_REQUEST)
                    return self._wyslij(s.pilot.status())
                if u.path != "/api/g/zaloguj":
                    return self._wyslij(None)
                ip = self.client_address[0]
                teraz = time.time()
                proby = [t for t in s.nieudane.get(ip, []) if teraz - t < 300]
                if len(proby) >= 8:
                    return self._wyslij({"blad": "Za dużo prób — spróbuj za 5 minut."}, kod=HTTPStatus.TOO_MANY_REQUESTS)
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    pin = str(json.loads(self.rfile.read(min(n, 1000)) or b"{}").get("pin", "")).strip()
                except (ValueError, AttributeError):
                    pin = ""
                if pin and secrets.compare_digest(pin, s.pin):
                    t = s.staly_token or secrets.token_urlsafe(24)
                    s.tokeny.add(t)
                    return self._wyslij({"t": t})
                time.sleep(1)
                s.nieudane[ip] = proby + [teraz]
                return self._wyslij({"blad": "Zły PIN"}, kod=HTTPStatus.UNAUTHORIZED)
        return H


def serwer_24h(folder: str, port: int = 8080, pin: str | None = None, baza: str | None = None,
               co_ile_h: float = 6.0) -> None:  # pragma: no cover - uruchamiane na Raspberry Pi
    """Tryb serwera: skanuje folder biblioteki (na starcie i co kilka godzin) i udostępnia galerię."""
    folder = os.path.abspath(folder)
    dane = Path(baza) if baza else Path.home() / ".katalogator-galeria"
    dane.mkdir(parents=True, exist_ok=True)
    plik_bazy = dane / "galeria.db"
    g = Galeria(plik_bazy, lambda: [folder], pamiec_min=dane / "miniatury")
    srv = SerwerGalerii(g, port=port, pin=pin).start()
    print(f"Galeria: {', '.join(srv.adresy())}  PIN: {srv.pin}", flush=True)
    while True:
        try:
            db = skaner.otworz_baze(plik_bazy)
            try:
                w = skaner.skanuj(folder, db, watki=4, wypisz=lambda *_: None)
                print(f"Skan: {w['wszystkie']} plików ({w['nowe_lub_zmienione']} nowych/zmienionych)", flush=True)
            finally:
                db.close()
        except Exception as e:
            print(f"Skan nieudany: {e}", flush=True)
        time.sleep(co_ile_h * 3600)
