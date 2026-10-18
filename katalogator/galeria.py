"""Przeglądarka biblioteki: oś czasu (lata → miesiące) i mapa miejsc (OpenStreetMap).

Działa w oknie programu (dane projektu) i jako osobny serwer tylko do odczytu dla telefonu —
z komputera (sieć domowa / Tailscale, z PIN-em) albo 24/7 z Raspberry Pi:
    python -m katalogator galeria --folder /mnt/mycloud/Biblioteka --pin 1234
"""

from __future__ import annotations

import datetime
import io
import json
import os
import re
import secrets
import socket
import sqlite3
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
CREATE TABLE IF NOT EXISTS g_udostepnione (token TEXT PRIMARY KEY, album INTEGER NOT NULL, czas REAL NOT NULL);
CREATE TABLE IF NOT EXISTS g_album_pliki (album INTEGER NOT NULL, sciezka TEXT NOT NULL, czas REAL NOT NULL,
                                          PRIMARY KEY (album, sciezka));
CREATE TABLE IF NOT EXISTS g_min_filmow (sciezka TEXT PRIMARY KEY, mtime REAL NOT NULL, dane BLOB NOT NULL);
CREATE INDEX IF NOT EXISTS g_album_pliki_sciezka ON g_album_pliki(sciezka);
"""
_MIESIACE_SZUKANIA = [("stycz", 1), ("lut", 2), ("mar", 3), ("kwie", 4), ("maj", 5), ("czerw", 6), ("lip", 7),
                      ("sierp", 8), ("wrze", 9), ("paźdz", 10), ("pazdz", 10), ("listop", 11), ("grud", 12)]
_NAZWY_MIES = ["styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec", "sierpień", "wrzesień",
               "październik", "listopad", "grudzień"]
_KOLUMNY = ("rowid id, wzgledna, rodzaj, data, lat, lon, rozmiar, "  # + 🗂 albumy, w których jest zdjęcie (znaczek na miniaturze)
            "(SELECT group_concat(n.nazwa, ' · ') FROM g_album_pliki a JOIN g_albumy n ON n.id = a.album "
            "WHERE a.sciezka = pliki.sciezka) albumy")
_PORY = {"rano": (5, 11), "dzien": (11, 17), "wieczor": (17, 22), "noc": (22, 5)}  # 🕐 godziny [od, do)
_UKR: dict = {}  # baza → (ukrywanie włączone, id ukrytych albumów) — wspólne dla wszystkich galerii tej bazy


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
            if "ukryty" not in {r[1] for r in db.execute("PRAGMA table_info(g_albumy)")}:  # od 1.35: 🙈 ukryte albumy
                db.execute("ALTER TABLE g_albumy ADD COLUMN ukryty INTEGER NOT NULL DEFAULT 0")
            db.execute("CREATE TABLE IF NOT EXISTS g_ustawienia (klucz TEXT PRIMARY KEY, wartosc TEXT)")
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

    def _warunek(self, obszar: tuple | None = None, ukryte: bool = True) -> tuple[str, list]:
        w, arg = self._zakres(ukryte)
        if obszar:  # prostokąt z mapy: (lat1, lat2, lon1, lon2)
            w += " AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?"
            arg = arg + [min(obszar[:2]), max(obszar[:2]), min(obszar[2:]), max(obszar[2:])]
        return w, arg

    def _rodzaj(self) -> str:
        """Filtr 📷 zdjęcia / 🎬 filmy / 📄 dokumenty z bieżącego zapytania (parametr r) — „” = wszystko."""
        r = getattr(_FILTR, "rodzaj", "")
        if not r:
            return ""
        if not hasattr(self, "_ma_dok"):
            db = skaner.otworz_baze(self.baza)
            try:
                self._ma_dok = bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='decyzje_dok'").fetchone())
            finally:
                db.close()
        # dokument: Twoja decyzja w projekcie albo zdjęcie w folderze „Dokumenty…” (np. Dokumenty z 2023)
        dok = ("((lower(wzgledna) LIKE '%dokument%' AND sciezka NOT IN (SELECT sciezka FROM decyzje_dok WHERE dokument=0))"
               " OR sciezka IN (SELECT sciezka FROM decyzje_dok WHERE dokument=1))") if self._ma_dok \
            else "(lower(wzgledna) LIKE '%dokument%')"
        return {"zdjecie": f" AND rodzaj='zdjecie' AND NOT {dok}", "film": " AND rodzaj='film'",
                "dokument": f" AND rodzaj='zdjecie' AND {dok}"}.get(r, "")

    @staticmethod
    def _kier(domyslna: str = "stare") -> str:
        """⇅ Kolejność z bieżącego zapytania (parametr kol): „nowe” = od najnowszych, „stare” = od najstarszych."""
        return "DESC" if (getattr(_FILTR, "kolejnosc", "") or domyslna) == "nowe" else "ASC"

    # --- 🙈 ukryte albumy (np. „Praca”): ich zdjęcia nie pokazują się na osi czasu, mapie, w szukaniu… -------
    def ukrywanie(self) -> tuple[bool, tuple]:
        """(włączone, id ukrytych albumów) — zapamiętane, odświeżane po każdej zmianie."""
        k = str(self.baza)
        if _UKR.get(k) is None:
            db = self._db()
            try:
                r = db.execute("SELECT wartosc FROM g_ustawienia WHERE klucz='ukrywanie'").fetchone()
                ids = tuple(x[0] for x in db.execute("SELECT id FROM g_albumy WHERE ukryty=1"))
            finally:
                db.close()
            _UKR[k] = (r is None or r[0] != "0", ids)
        return _UKR[k]

    def _bez_ukrytych(self) -> str:
        wl, ids = self.ukrywanie()
        if not wl or not ids:
            return ""
        return (" AND sciezka NOT IN (SELECT sciezka FROM g_album_pliki WHERE album IN (%s))"
                % ",".join(str(int(i)) for i in ids))

    def album_ukryj(self, album: int, tak: bool = True) -> dict:
        db = self._db()
        try:
            db.execute("UPDATE g_albumy SET ukryty=? WHERE id=?", (1 if tak else 0, int(album)))
            db.commit()
        finally:
            db.close()
        _UKR.pop(str(self.baza), None)
        return {"ok": True, "ukryty": bool(tak)}

    def ustaw_ukrywanie(self, wlacz: bool) -> dict:
        db = self._db()
        try:
            db.execute("INSERT OR REPLACE INTO g_ustawienia VALUES ('ukrywanie', ?)", ("1" if wlacz else "0",))
            db.commit()
        finally:
            db.close()
        _UKR.pop(str(self.baza), None)
        return {"ok": True, "ukrywanie": bool(wlacz)}

    @staticmethod
    def _filtry(bez_aparatu: bool = False) -> tuple[str, list]:
        """📷 aparat i 🕐 pora dnia z bieżącego zapytania (parametry ap, pora)."""
        sql, arg = "", []
        ap = getattr(_FILTR, "aparat", None)
        if ap is not None and not bez_aparatu:
            if ap:
                sql += " AND aparat = ?"; arg.append(ap)
            else:
                sql += " AND coalesce(aparat, '') = ''"
        p = getattr(_FILTR, "pora", "")
        if p in _PORY:
            od, do = _PORY[p]
            godz = "CAST(substr(data, 12, 2) AS INTEGER)"
            sql += f" AND length(data) >= 13 AND " + (f"({godz} >= {od} OR {godz} < {do})" if od > do
                                                      else f"{godz} >= {od} AND {godz} < {do}")
        return sql, arg

    def aparaty(self) -> dict:
        """Aparaty i telefony w bieżącym widoku (z liczbą zdjęć) — do filtra 📷."""
        _FILTR.bez_aparatu = True
        try:
            w, arg = self._warunek()
        finally:
            _FILTR.bez_aparatu = False
        db = self._db()
        try:
            r = db.execute(f"SELECT coalesce(aparat, '') a, COUNT(*) n FROM pliki WHERE rodzaj IN ('zdjecie','film') {w} "
                           "GROUP BY a ORDER BY n DESC", arg).fetchall()
        finally:
            db.close()
        return {"aparaty": [[x["a"], x["n"]] for x in r]}

    def _zakres(self, ukryte: bool = True) -> tuple[str, list]:
        u = self._bez_ukrytych() if ukryte else ""
        fs, fa = self._filtry(getattr(_FILTR, "bez_aparatu", False))
        u += fs
        k = self.korzenie()
        if k is None:  # wszystko w bazie
            return self.filtr + self._rodzaj() + u, fa
        if not k:  # zakres pusty (np. biblioteka, gdy nie wybrano miejsca docelowego)
            return " AND 0", []
        czesci, arg = [], []
        for r in k:
            r = os.path.abspath(r)
            pref = r.rstrip("\\/") + os.sep
            czesci.append("(korzen = ? OR substr(sciezka, 1, ?) = ?)")
            arg += [r, len(pref), pref]
        return " AND (" + " OR ".join(czesci) + ")" + self.filtr + self._rodzaj() + u, arg + fa

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
        k = self._kier()
        a = [str(rok)] + ([int(miesiac)] if miesiac else [])
        db = self._db()
        try:
            razem = db.execute(f"SELECT COUNT(*) FROM pliki WHERE rodzaj IN ('zdjecie','film') AND {filtr} {w}",
                               a + arg).fetchone()[0]
            wiersze = [dict(r) for r in db.execute(
                f"""SELECT {_KOLUMNY} FROM pliki
                    WHERE rodzaj IN ('zdjecie','film') AND {filtr} {w} ORDER BY data {k}, wzgledna {k} LIMIT ? OFFSET ?""",
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
        w, arg = self._warunek(ukryte=not getattr(_FILTR, "okno", False))
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
            nazwy_alb = [x[0] for x in db.execute("SELECT n.nazwa FROM g_album_pliki a JOIN g_albumy n ON n.id=a.album "
                                                   "WHERE a.sciezka=?", (r["sciezka"],))]
            try:
                d = db.execute("SELECT dokument FROM decyzje_dok WHERE sciezka=?", (r["sciezka"],)).fetchone()
            except sqlite3.OperationalError:
                d = None
            dokument = bool(d[0]) if d else "dokument" in r["wzgledna"].lower()
        finally:
            db.close()
        return {"id": r["id"], "nazwa": re.split(r"[\\/]", r["wzgledna"])[-1], "folder": os.path.dirname(r["wzgledna"]),
                "data": r["data"], "rodzaj": r["rodzaj"], "aparat": r["aparat"], "lat": r["lat"], "lon": r["lon"],
                "miejsce": miejsce, "rozmiar": r["rozmiar"], "ulubione": ulub, "albumy": albumy, "dokument": dokument,
                "nazwy_albumow": nazwy_alb}

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
                if r and abs(r["mtime"] - os.path.getmtime(film)) < 1:
                    return r["dane"]
            except OSError:
                return None
            # każdy format (także stare AVI/MPG/3GP/WMV) — klatka z ffmpeg, zapamiętana w bazie galerii
            from . import filmy
            jpeg = filmy.klatka(film, 480)
            if jpeg:
                self.zapisz_miniature_filmu(id_, jpeg)
            return jpeg
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
        osoby_ids, osoby_nazwy = [], []
        if reszta:  # 👤 imię osoby (z widoku „Osoby”)
            from . import twarze
            db = self._db()
            try:
                for s in list(reszta):
                    o = twarze.osoba_w_tekscie(db, s)
                    if o:
                        osoby_ids.append(o); reszta.remove(s)
                        osoby_nazwy.append(db.execute("SELECT nazwa FROM g_osoby WHERE id=?", (o,)).fetchone()[0])
            finally:
                db.close()
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
        if not (rok or mies or miejsce or tekstowe or osoby_ids):
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
        for o in osoby_ids:
            war.append("sciezka IN (SELECT sciezka FROM g_twarze WHERE osoba=?)"); a.append(o)
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
                wiersze = [dict(r) for r in db.execute(f"SELECT {_KOLUMNY} {sql} ORDER BY data {self._kier('nowe')}",
                                                       arg + a)]
                cel = miejsce["nazwa"] if miejsce["pl"] else "@" + miejsce["kraj"]

                def pasuje(r):
                    e = miejsca.etykieta(r["lat"], r["lon"])
                    return e == cel or (miejsce["kraj"] == "PL" and not e.startswith("@"))
                wiersze = [r for r in wiersze if pasuje(r)]
                razem, wiersze = len(wiersze), wiersze[od:od + ile]
            else:
                razem = db.execute(f"SELECT COUNT(*) {sql}", arg + a).fetchone()[0]
                wiersze = [dict(r) for r in db.execute(f"SELECT {_KOLUMNY} {sql} ORDER BY data {self._kier('nowe')} "
                                                       f"LIMIT ? OFFSET ?",
                                                       arg + a + [int(ile), int(od)])]
        finally:
            db.close()
        opis = [f"👤 {n}" for n in osoby_nazwy] + ([miejsce["nazwa"]] if miejsce else [])
        if mies:
            opis.append(_NAZWY_MIES[mies - 1] + (f" {rok}" if rok else ""))
        elif rok:
            opis.append(rok)
        opis += [f"„{s}”" for s in tekstowe]
        return {"razem": razem, "pliki": [_nazwa(r) for r in wiersze], "opis": " · ".join(opis)}

    # --- ten dzień lata temu ------------------------------------------------------------------------------
    def tego_dnia(self, md: str | None = None, dni: int = 0) -> dict:
        """Zdjęcia i filmy z tego samego dnia (± `dni`) w poprzednich latach, od najnowszych — pogrupowane latami.
        Gdy nic nie ma, podpowiada najbliższy dzień roku, z którego są zdjęcia."""
        md = md if md and re.fullmatch(r"\d\d-\d\d", md) else time.strftime("%m-%d")
        dni = max(0, min(int(dni or 0), 15))
        try:
            srodek = datetime.date(2024, int(md[:2]), int(md[3:]))  # rok przestępny: 29 lutego też istnieje
        except ValueError:
            md, srodek = time.strftime("%m-%d"), datetime.date(2024, *map(int, time.strftime("%m-%d").split("-")))
        dni_md = sorted({(srodek + datetime.timedelta(days=d)).strftime("%m-%d") for d in range(-dni, dni + 1)})
        w, arg = self._warunek()
        teraz = time.strftime("%Y")
        db = self._db()
        try:
            wiersze = [dict(r) for r in db.execute(
                f"""SELECT {_KOLUMNY} FROM pliki WHERE rodzaj IN ('zdjecie','film')
                    AND substr(data, 6, 5) IN ({','.join('?' * len(dni_md))}) AND substr(data, 1, 4) < ? {w}
                    ORDER BY substr(data, 1, 4) {self._kier('nowe')}, data LIMIT 2000""", dni_md + [teraz] + arg)]
            najblizszy = None
            if not wiersze:  # podpowiedź: najbliższy dzień roku ze zdjęciami z poprzednich lat
                dzien_roku = srodek.timetuple().tm_yday
                kandydaci = []
                for r in db.execute(f"""SELECT substr(data, 6, 5) md, COUNT(*) n FROM pliki
                                        WHERE rodzaj IN ('zdjecie','film') AND data IS NOT NULL
                                        AND substr(data, 1, 4) < ? {w} GROUP BY 1""", [teraz] + arg):
                    try:
                        d = datetime.date(2024, int(r["md"][:2]), int(r["md"][3:])).timetuple().tm_yday
                    except ValueError:
                        continue
                    odl = min(abs(d - dzien_roku), 366 - abs(d - dzien_roku))
                    kandydaci.append((odl, r["md"], r["n"]))
                if kandydaci:
                    odl, n_md, n = min(kandydaci)
                    najblizszy = {"md": n_md, "n": n, "dni": odl}
        finally:
            db.close()
        lata: dict[str, int] = {}
        for r in wiersze:
            lata[r["data"][:4]] = lata.get(r["data"][:4], 0) + 1
        return {"md": md, "dni": dni, "razem": len(wiersze),
                "lata": [{"rok": k, "n": v, "lat_temu": int(teraz) - int(k)} for k, v in lata.items()],
                "pliki": [_nazwa(r) for r in wiersze], "najblizszy": najblizszy}

    # --- 🗑 usuwanie: do kosza programu (Odłożone/Usunięte), z cofaniem ------------------------------------------
    def usun(self, ids: list[int]) -> dict:
        from . import usuwanie
        w, arg = self._warunek()
        db = self._db()
        try:
            dozwolone = [int(i) for i in ids[:5000]
                         if db.execute(f"SELECT 1 FROM pliki WHERE rowid=? {w}", [int(i)] + arg).fetchone()]
            if not dozwolone:
                return {"blad": "Nie ma takiego pliku — odśwież widok."}
            return usuwanie.usun(db, dozwolone)
        finally:
            db.close()

    def lokalizacja(self, ids: list[int], lat, lon) -> dict:
        """📍 Dodaj / zmień (np. przesunięta pinezka) / usuń (lat=None) lokalizację — w pliku i w bazie."""
        from . import lokalizacja
        w, arg = self._warunek()
        db = self._db()
        try:
            dozwolone = [int(i) for i in ids[:2000]
                         if db.execute(f"SELECT 1 FROM pliki WHERE rowid=? {w}", [int(i)] + arg).fetchone()]
            if not dozwolone:
                return {"blad": "Nie ma takiego pliku — odśwież widok."}
            try:
                return lokalizacja.ustaw(db, dozwolone, None if lat is None else float(lat),
                                         None if lat is None else float(lon))
            except (TypeError, ValueError):
                return {"blad": "Nieprawidłowe współrzędne."}
        finally:
            db.close()

    def data(self, ids: list[int], tekst: str) -> dict:
        """📅 Zmiana daty zrobienia — w pliku (EXIF albo .xmp obok) i w bazie."""
        from . import lokalizacja
        w, arg = self._warunek()
        db = self._db()
        try:
            dozwolone = [int(i) for i in ids[:2000]
                         if db.execute(f"SELECT 1 FROM pliki WHERE rowid=? {w}", [int(i)] + arg).fetchone()]
            if not dozwolone:
                return {"blad": "Nie ma takiego pliku — odśwież widok."}
            return lokalizacja.ustaw_date(db, dozwolone, tekst)
        finally:
            db.close()

    def dokument(self, ids: list[int], tak: bool, przenies: bool = True) -> dict:
        """📄 To zdjęcie to dokument (albo jednak zwykłe zdjęcie) — filtr „Dokumenty” i projekt widzą decyzję.
        W uporządkowanej bibliotece plik od razu trafia do właściwego folderu (Dokumenty/Dokumenty z RRRR ⇄
        Zdjęcia/Zdjęcia z RRRR/<Miesiąc…>) — `ruchy` pozwalają to cofnąć."""
        w, arg = self._warunek(ukryte=False)
        db = self._db()
        sciezki = []
        try:
            db.execute("CREATE TABLE IF NOT EXISTS decyzje_dok (sciezka TEXT PRIMARY KEY, dokument INTEGER NOT NULL)")
            for i in ids[:5000]:
                r = db.execute(f"SELECT rowid id, sciezka, rodzaj, data, lat, lon FROM pliki WHERE rowid=? {w}",
                               [int(i)] + arg).fetchone()
                if r:
                    db.execute("INSERT OR REPLACE INTO decyzje_dok VALUES (?, ?)", (r["sciezka"], 1 if tak else 0))
                    sciezki.append(dict(r))
            db.commit()
            self._ma_dok = True
        finally:
            db.close()
        ruchy, bledy, foldery = [], [], set()
        if przenies:
            for r in sciezki:
                if r["rodzaj"] != "zdjecie":
                    continue
                cel = folder_w_bibliotece(r, tak)
                if not cel:
                    continue
                w2 = self.przenies_plik(r["id"], cel)
                if w2.get("blad"):
                    bledy.append(w2["blad"])
                elif w2.get("sciezka") != r["sciezka"]:
                    ruchy.append({"id": r["id"], "z": r["sciezka"], "do": w2["sciezka"]})
                    foldery.add(os.path.relpath(cel, biblioteka_pliku(r["sciezka"]) or cel))
        return {"zmienione": len(sciezki), "dokument": bool(tak), "ruchy": ruchy, "bledy": bledy, "foldery": sorted(foldery)}

    def przenies_plik(self, id_: int, folder: str = "", sciezka: str = "") -> dict:
        """Przenosi plik (do folderu albo dokładnie pod `sciezka` — „Cofnij”) i poprawia bazę: ulubione, albumy, osoby…"""
        import shutil
        from . import edycja
        r = self._wiersz(id_)
        if not r or not os.path.isfile(r["sciezka"]):
            return {"blad": "Nie ma pliku (odłączony dysk?)."}
        sc = r["sciezka"]
        if sciezka:
            docel = sciezka
            if os.path.exists(docel):
                return {"blad": f"W tym miejscu jest już plik: {os.path.basename(docel)}"}
        else:
            if os.path.normcase(os.path.dirname(sc)) == os.path.normcase(os.path.abspath(folder)):
                return {"ok": True, "sciezka": sc}
            rdzen, rozsz = os.path.splitext(os.path.basename(sc))
            docel = edycja.wolna_nazwa(folder, rdzen, rozsz)
        try:
            os.makedirs(os.path.dirname(docel), exist_ok=True)
            shutil.move(sc, docel)
            if os.path.isfile(sc + ".xmp"):
                shutil.move(sc + ".xmp", docel + ".xmp")
        except OSError as e:
            return {"blad": f"{os.path.basename(sc)}: {e.strerror or e}"}
        self._w_bazie(r, docel)
        stary = os.path.dirname(sc)  # pusty folder po przeniesieniu (np. stary miesiąc) — sprzątamy
        try:
            if not os.listdir(stary):
                os.rmdir(stary)
        except OSError:
            pass
        return {"ok": True, "sciezka": docel}

    def _w_bazie(self, r, docel: str) -> None:
        """Nowa ścieżka pliku w bazie — w `pliki` i we wszystkich tabelach z kolumną `sciezka`."""
        sc = r["sciezka"]
        db = self._db()
        try:
            try:
                wz = os.path.relpath(docel, r["korzen"])
            except ValueError:  # inny dysk niż korzeń skanu
                wz = docel
            db.execute("UPDATE pliki SET sciezka=?, wzgledna=? WHERE rowid=?", (docel, wz, r["id"]))
            for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'pliki'").fetchall():
                if "sciezka" in {c[1] for c in db.execute(f'PRAGMA table_info("{t}")')}:  # ulubione, albumy, twarze…
                    db.execute(f'UPDATE OR IGNORE "{t}" SET sciezka=? WHERE sciezka=?', (docel, sc))
            db.commit()
        finally:
            db.close()
        self._zapomnij_miniatury(r["id"])

    # --- ✏ edycja zdjęcia: kopia obok albo w miejsce oryginału (oryginał do kosza programu) ---------------------
    def _zapomnij_miniatury(self, *ids) -> None:
        with self._blokada:
            for i in ids:
                for sr in (False, True):
                    self._min.pop((int(i), sr), None)

    def edytuj(self, id_: int, op: dict, zastap: bool = False) -> dict:
        from . import edycja
        r = self._wiersz(id_)
        if not r or r["rodzaj"] != "zdjecie":
            return {"blad": "Nie ma takiego zdjęcia — odśwież widok."}
        db = self._db()
        try:
            w = edycja.zapisz(db, r, op, zastap)
            if w.get("id"):
                self._zapomnij_miniatury(id_, w["id"])
                n = db.execute(f"SELECT {_KOLUMNY} FROM pliki WHERE rowid=?", (w["id"],)).fetchone()
                w["plik"] = _nazwa(dict(n)) if n else None
            return w
        finally:
            db.close()

    def edytuj_cofnij(self, id_: int, partia: int | None) -> dict:
        from . import edycja
        if not self._wiersz(id_):
            return {"blad": "Nie ma takiego pliku — odśwież widok."}
        db = self._db()
        try:
            self._zapomnij_miniatury(id_)
            return edycja.cofnij(db, id_, partia)
        finally:
            db.close()

    # --- ⬇ ZIP: zaznaczone albo cały album (oryginały) -------------------------------------------------
    def pliki_zip(self, ids=None, album: int | None = None) -> list[str]:
        w, arg = self._warunek()
        db = self._db()
        try:
            if album:
                self._napraw_kolekcje(db)
                return [r[0] for r in db.execute(
                    f"""SELECT sciezka FROM pliki WHERE rodzaj IN ('zdjecie','film') AND sciezka IN
                        (SELECT sciezka FROM g_album_pliki WHERE album=?) {w} ORDER BY data, wzgledna""",
                    [int(album)] + arg)]
            wynik = []
            for i in list(ids or [])[:5000]:
                r = db.execute(f"SELECT sciezka FROM pliki WHERE rowid=? AND rodzaj IN ('zdjecie','film') {w}",
                               [int(i)] + arg).fetchone()
                if r:
                    wynik.append(r[0])
            return wynik
        finally:
            db.close()

    def nazwa_albumu(self, album: int) -> str:
        db = self._db()
        try:
            r = db.execute("SELECT nazwa FROM g_albumy WHERE id=?", (int(album),)).fetchone()
            return r[0] if r else "Album"
        finally:
            db.close()

    def cofnij_usuniecie(self, partia: int) -> dict:
        from . import usuwanie
        db = self._db()
        try:
            return usuwanie.cofnij(db, partia)
        finally:
            db.close()

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
        wa, arga = self._warunek(ukryte=False)  # licznik zdjęć w samym albumie (także ukrytym)
        wl, ukryte = self.ukrywanie()
        okno = getattr(_FILTR, "okno", False)
        db = self._db()
        try:
            self._napraw_kolekcje(db)
            wynik = []
            for a in db.execute("SELECT id, nazwa, ukryty FROM g_albumy ORDER BY czas DESC").fetchall():
                if a["ukryty"] and wl and not okno:  # telefon / serwer 24/7: ukrytych albumów nie widać wcale
                    continue
                r = db.execute(f"""SELECT COUNT(*) n, MIN(rowid) okladka FROM pliki WHERE rodzaj IN ('zdjecie','film')
                                   AND sciezka IN (SELECT sciezka FROM g_album_pliki WHERE album=?) {wa}""",
                               [a["id"]] + arga).fetchone()
                t = db.execute("SELECT token FROM g_udostepnione WHERE album=?", (a["id"],)).fetchone()
                wynik.append({"id": a["id"], "nazwa": a["nazwa"], "n": r["n"], "okladka": r["okladka"],
                              "udostepniony": bool(t), "ukryty": bool(a["ukryty"])})
            u = db.execute(f"""SELECT COUNT(*) n, MIN(rowid) okladka FROM pliki WHERE rodzaj IN ('zdjecie','film')
                               AND sciezka IN (SELECT sciezka FROM g_ulubione) {w}""", arg).fetchone()
        finally:
            db.close()
        return {"albumy": wynik, "ulubione": {"n": u["n"], "okladka": u["okladka"]}, "ukrywanie": wl,
                "ukrytych": len(ukryte)}

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

    # --- 🔗 udostępnianie albumu linkiem (bez PIN-u, tylko ten album, tylko do oglądania) ----------------------
    def udostepnij(self, album: int, wlacz: bool = True) -> dict:
        db = self._db()
        try:
            if not db.execute("SELECT 1 FROM g_albumy WHERE id=?", (int(album),)).fetchone():
                return {"blad": "nie ma takiego albumu"}
            if not wlacz:
                db.execute("DELETE FROM g_udostepnione WHERE album=?", (int(album),))
                db.commit()
                return {"token": None}
            r = db.execute("SELECT token FROM g_udostepnione WHERE album=?", (int(album),)).fetchone()
            if r:
                return {"token": r[0]}
            t = secrets.token_urlsafe(16)
            db.execute("INSERT INTO g_udostepnione VALUES (?,?,?)", (t, int(album), time.time()))
            db.commit()
            return {"token": t}
        finally:
            db.close()

    def album_tokenu(self, token: str) -> int | None:
        if not token or len(token) > 64:
            return None
        db = self._db()
        try:
            r = db.execute("SELECT album FROM g_udostepnione WHERE token=?", (token,)).fetchone()
            return r[0] if r else None
        finally:
            db.close()

    def w_albumie(self, album: int, id_: int) -> bool:
        db = self._db()
        try:
            return db.execute("""SELECT 1 FROM pliki p JOIN g_album_pliki a ON a.sciezka = p.sciezka
                                 WHERE p.rowid=? AND a.album=?""", (int(id_), int(album))).fetchone() is not None
        finally:
            db.close()

    def album_usun(self, album: int) -> dict:  # tylko album — zdjęcia zostają na dysku
        db = self._db()
        try:
            db.execute("DELETE FROM g_udostepnione WHERE album=?", (int(album),))
            db.execute("DELETE FROM g_album_pliki WHERE album=?", (int(album),))
            db.execute("DELETE FROM g_albumy WHERE id=?", (int(album),))
            db.commit()
            _UKR.pop(str(self.baza), None)
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
                r = db.execute("SELECT nazwa, ukryty FROM g_albumy WHERE id=?", (int(album),)).fetchone()
                if not r or (r["ukryty"] and self.ukrywanie()[0] and not getattr(_FILTR, "okno", False)):
                    return {"blad": "nie ma takiego albumu"}
                nazwa = r[0]
                if r["ukryty"]:  # sam ukryty album pokazuje swoje zdjęcia
                    w, arg = self._warunek(ukryte=False)
            self._napraw_kolekcje(db)
            sql = f"FROM pliki WHERE rodzaj IN ('zdjecie','film') AND sciezka IN ({pod}) {w}"
            razem = db.execute(f"SELECT COUNT(*) {sql}", a + arg).fetchone()[0]
            k = self._kier()
            wiersze = [dict(r) for r in db.execute(f"SELECT {_KOLUMNY} {sql} ORDER BY data {k}, wzgledna {k} "
                                                   f"LIMIT ? OFFSET ?", a + arg + [int(ile), int(od)])]
        finally:
            db.close()
        return {"razem": razem, "pliki": [_nazwa(r) for r in wiersze], "nazwa": nazwa}

    # --- 📦 eksport (zmniejszone kopie do wysłania) i ✎ zmiana nazw hurtem ---------------------------------
    def eksportuj(self, id_: int, cel: str, bok: int = 2048, jakosc: int = 88, bez_gps: bool = True,
                  znak: str = "") -> dict:
        import shutil

        from PIL import Image, ImageOps

        from . import edycja
        r = self._wiersz(id_)
        if not r or r["rodzaj"] not in ("zdjecie", "film") or not os.path.isfile(r["sciezka"]):
            return {"blad": "Nie ma pliku (odłączony dysk?)."}
        if not cel or not os.path.isdir(cel):
            return {"blad": "Folder docelowy nie istnieje."}
        sc = r["sciezka"]
        rdzen, rozsz = os.path.splitext(os.path.basename(sc))
        try:
            if r["rodzaj"] == "film":  # filmy — kopia bez zmian
                docel = edycja.wolna_nazwa(cel, rdzen, rozsz.lower())
                shutil.copy2(sc, docel)
                return {"ok": True, "plik": docel}
            with Image.open(sc) as org:
                ex = org.getexif()
                im = ImageOps.exif_transpose(org).convert("RGB")
            if bok and max(im.size) > bok:
                im.thumbnail((int(bok), int(bok)), Image.LANCZOS)
            if znak.strip():
                im = _znak_wodny(im, znak.strip()[:80])
            ex[0x0112] = 1
            for t in (0x0201, 0x0202):
                ex.pop(t, None)
            if bez_gps:
                ex.pop(0x8825, None)  # 📍 współrzędne zostają u Ciebie
            if r["data"] and len(r["data"]) >= 19:  # data także w kopii z HEIC/PNG (gdy była tylko w .xmp)
                sz = ex.get_ifd(0x8769)
                if 0x9003 not in sz:
                    sz[0x9003] = r["data"][:19].replace("-", ":", 2).replace("T", " ")
            docel = edycja.wolna_nazwa(cel, rdzen, ".jpg")
            im.save(docel, "JPEG", quality=max(40, min(100, int(jakosc))), optimize=True, exif=ex.tobytes())
        except Exception as e:  # noqa: BLE001
            return {"blad": f"{os.path.basename(sc)}: {e}"}
        return {"ok": True, "plik": docel}

    def nazwy_podglad(self, ids: list[int], wzor: str, start: int = 1) -> dict:
        """✎ Nowe nazwy według wzorca: {data} {czas} {rok} {mies} {dzien} {miejsce} {aparat} {folder} {nazwa} {nr}."""
        wynik, szer = [], max(3, len(str(start + len(ids) - 1)))
        zajete: set = set()
        for n, i in enumerate(ids):
            r = self._wiersz(i)
            if not r:
                continue
            stara = os.path.basename(r["sciezka"])
            rdzen, rozsz = os.path.splitext(stara)
            d = r["data"] or ""
            miejsce = ""
            if r["lat"] is not None:
                try:
                    e = miejsca.etykieta(r["lat"], r["lon"])
                    miejsce = e[1:] if e.startswith("@") else e
                except Exception:  # noqa: BLE001
                    pass
            pola = {"data": d[:10], "czas": d[11:19].replace(":", "-"), "rok": d[:4], "mies": d[5:7], "dzien": d[8:10],
                    "miejsce": miejsce, "aparat": r["aparat"] or "", "nazwa": rdzen, "nr": str(start + n).zfill(szer),
                    "folder": os.path.basename(os.path.dirname(r["sciezka"]))}
            nowa = re.sub(r"\{(\w+)\}", lambda m: pola.get(m.group(1), m.group(0)), wzor or "{nazwa}")
            nowa = re.sub(r'[\\/:*?"<>|]+', "-", nowa).strip(" .-_") or rdzen
            nowa = re.sub(r"[-_ ]{2,}", lambda m: m.group(0)[0], nowa) + rozsz
            docel = os.path.join(os.path.dirname(r["sciezka"]), nowa)
            konflikt = (nowa.lower() != stara.lower() and os.path.exists(docel)) or docel.lower() in zajete
            zajete.add(docel.lower())
            wynik.append({"id": r["id"], "stara": stara, "nowa": nowa, "konflikt": konflikt})
        return {"nazwy": wynik}

    def zmien_nazwe(self, id_: int, nowa: str) -> dict:
        r = self._wiersz(id_)
        if not r or not os.path.isfile(r["sciezka"]):
            return {"blad": "Nie ma pliku (odłączony dysk?)."}
        sc, stara = r["sciezka"], os.path.basename(r["sciezka"])
        nowa = str(nowa or "").strip()
        if not nowa or re.search(r'[\\/:*?"<>|]', nowa) or len(nowa) > 200 or nowa in (".", ".."):
            return {"blad": f"Niedozwolona nazwa: „{nowa}”"}
        if os.path.splitext(nowa)[1].lower() != os.path.splitext(stara)[1].lower():
            nowa += os.path.splitext(stara)[1]
        docel = os.path.join(os.path.dirname(sc), nowa)
        if docel == sc:
            return {"ok": True, "id": r["id"], "nazwa": nowa, "stara": stara}
        if os.path.exists(docel) and nowa.lower() != stara.lower():
            return {"blad": f"Plik „{nowa}” już jest w tym folderze."}
        try:
            os.rename(sc, docel)
            if os.path.isfile(sc + ".xmp"):  # data / miejsce zapisane obok — razem z plikiem
                os.replace(sc + ".xmp", docel + ".xmp")
        except OSError as e:
            return {"blad": f"Nie udało się zmienić nazwy: {e.strerror or e}"}
        self._w_bazie(r, docel)
        return {"ok": True, "id": r["id"], "nazwa": nowa, "stara": stara}

    # --- 🔀 serie: kilka ujęć tej samej sceny zrobionych w ciągu paru sekund (ten sam folder) ----------------
    PRZERWA_SERII = 6  # s — dłuższa przerwa między zdjęciami = nowa seria

    @staticmethod
    def _sekundy(d: str | None) -> float | None:
        from datetime import datetime
        try:
            return datetime.fromisoformat(d[:19]).timestamp() if d and len(d) >= 19 else None
        except ValueError:
            return None

    def _lancuchy(self, wiersze) -> list[list]:
        """Kolejne zdjęcia z tego samego folderu, każde najwyżej PRZERWA_SERII s po poprzednim → seria (≥ 2)."""
        grupy, biez, poprz = [], [], None
        for r in wiersze:
            t, fol = self._sekundy(r["data"]), os.path.dirname(r["sciezka"])
            if biez and poprz and t is not None and poprz[0] is not None and fol == poprz[1] and 0 <= t - poprz[0] <= self.PRZERWA_SERII:
                biez.append(r)
            else:
                if len(biez) >= 2:
                    grupy.append(biez)
                biez = [r]
            poprz = (t, fol)
        if len(biez) >= 2:
            grupy.append(biez)
        return grupy

    def serie(self, od: int = 0, ile: int = 120) -> dict:
        w, arg = self._warunek()
        db = self._db()
        try:
            wiersze = db.execute(f"SELECT rowid id, sciezka, data FROM pliki WHERE rodzaj='zdjecie' AND length(data) >= 19 {w} "
                                 "ORDER BY data, sciezka", arg).fetchall()
        finally:
            db.close()
        grupy = self._lancuchy(wiersze)
        if self._kier("nowe") == "DESC":
            grupy.reverse()
        return {"razem": len(grupy), "zdjec": sum(len(x) for x in grupy),
                "serie": [{"ids": [r["id"] for r in x], "n": len(x), "data": x[0]["data"],
                           "folder": os.path.basename(os.path.dirname(x[0]["sciezka"]))} for x in grupy[od:od + ile]]}

    def seria(self, id_: int) -> dict:
        """Seria, do której należy zdjęcie (albo samo zdjęcie) — do porównania obok siebie."""
        r = self._wiersz(id_)
        t = self._sekundy(r["data"]) if r else None
        if not r or t is None:
            return {"ids": [int(id_)] if r else []}
        from datetime import datetime, timedelta
        d0 = datetime.fromtimestamp(t)
        w, arg = self._warunek()
        db = self._db()
        try:
            wiersze = db.execute(f"SELECT rowid id, sciezka, data FROM pliki WHERE rodzaj='zdjecie' AND data BETWEEN ? AND ? {w} "
                                 "ORDER BY data, sciezka", [(d0 - timedelta(minutes=10)).isoformat(),
                                                            (d0 + timedelta(minutes=10)).isoformat()] + arg).fetchall()
        finally:
            db.close()
        for x in self._lancuchy(wiersze):
            if any(y["id"] == int(id_) for y in x):
                return {"ids": [y["id"] for y in x]}
        return {"ids": [int(id_)]}

    def ostrosc(self, ids: list[int]) -> dict:
        """Ostrość (krawędzie na zmniejszonym zdjęciu) — podpowiedź przy wyborze najlepszego ujęcia."""
        out = {}
        for i in ids[:12]:
            sc = self.sciezka(i, "zdjecie")
            if not sc:
                continue
            try:
                im, _ = analiza.miniatura(sc, min_bok=600)
                out[str(i)] = round(analiza.ostrosc(im), 1)
            except Exception:  # noqa: BLE001
                pass
        return {"ostrosc": out}

    # --- 🌳 drzewo folderów: gdzie leżą zdjęcia i filmy ----------------------------------------------------
    def foldery(self) -> dict:
        """Każdy folder ze zdjęciami/filmami i ich liczba (bez podfolderów) — drzewo składa przeglądarka."""
        from collections import Counter
        w, arg = self._warunek()
        db = self._db()
        try:
            ile = Counter(os.path.dirname(r[0]) for r in db.execute(
                f"SELECT sciezka FROM pliki WHERE rodzaj IN ('zdjecie','film') {w}", arg))
        finally:
            db.close()
        return {"foldery": sorted([f, n] for f, n in ile.items())}

    def folder(self, sciezka: str, podfoldery: bool = False, od: int = 0, ile: int = 200) -> dict:
        sep = "\\" if "\\" in sciezka else "/"
        pref = sciezka.rstrip("\\/") + sep
        w, arg = self._warunek()
        war, a = "substr(sciezka, 1, ?) = ?", [len(pref), pref]
        if not podfoldery:  # tylko ten folder: w reszcie ścieżki nie ma już separatora
            war += " AND instr(substr(sciezka, ?), ?) = 0"
            a += [len(pref) + 1, sep]
        sql = f"FROM pliki WHERE rodzaj IN ('zdjecie','film') AND {war} {w}"
        k = self._kier("nowe")
        db = self._db()
        try:
            razem = db.execute(f"SELECT COUNT(*) {sql}", a + arg).fetchone()[0]
            wiersze = [dict(x) for x in db.execute(f"SELECT {_KOLUMNY} {sql} ORDER BY data {k}, wzgledna {k} "
                                                   f"LIMIT ? OFFSET ?", a + arg + [int(ile), int(od)])]
        finally:
            db.close()
        return {"razem": razem, "pliki": [_nazwa(x) for x in wiersze],
                "nazwa": os.path.basename(sciezka.rstrip("\\/")) or sciezka}

    # --- 👤 osoby (twarze) ----------------------------------------------------------------------------------
    def osoba(self, osoba: int, od: int = 0, ile: int = 200) -> dict:
        from . import twarze
        w, arg = self._warunek()
        db = self._db()
        try:
            twarze.przygotuj(db)
            r = db.execute("SELECT nazwa FROM g_osoby WHERE id=?", (int(osoba),)).fetchone()
            if not r:
                return {"blad": "nie ma takiej osoby"}
            sql = f"FROM pliki WHERE rodzaj='zdjecie' AND sciezka IN ({twarze.sciezki_osoby_sql()}) {w}"
            razem = db.execute(f"SELECT COUNT(*) {sql}", [int(osoba)] + arg).fetchone()[0]
            k = self._kier("nowe")
            wiersze = [dict(x) for x in db.execute(f"SELECT {_KOLUMNY} {sql} ORDER BY data {k}, wzgledna {k} "
                                                   f"LIMIT ? OFFSET ?", [int(osoba)] + arg + [int(ile), int(od)])]
        finally:
            db.close()
        return {"razem": razem, "pliki": [_nazwa(x) for x in wiersze], "nazwa": r[0] or "Bez imienia"}

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

    def wlasciwosci(self, id_: int) -> dict:
        """ℹ Właściwości: gdzie leży plik, rozmiar, wymiary, skąd data, aparat, miejsce, osoby."""
        r = self._wiersz(id_)
        if not r:
            return {"blad": "nie ma takiego pliku"}
        sc = r["sciezka"]
        d = {"sciezka": sc, "folder": os.path.dirname(sc), "nazwa": os.path.basename(sc), "rodzaj": r["rodzaj"],
             "rozmiar": r["rozmiar"], "zmieniony": r["mtime"], "data": r["data"], "zrodlo_daty": r["zrodlo_daty"],
             "aparat": r["aparat"], "lat": r["lat"], "lon": r["lon"], "istnieje": os.path.isfile(sc)}
        if r["lat"] is not None:
            try:
                e = miejsca.etykieta(r["lat"], r["lon"])
                d["miejsce"] = e if not e.startswith("@") else miejsca.fraza(e)
            except Exception:  # noqa: BLE001
                pass
        if d["istnieje"]:
            if r["rodzaj"] == "zdjecie":
                try:
                    from PIL import Image
                    with Image.open(sc) as im:  # tylko nagłówek — szybko
                        d["szer"], d["wys"], d["format"] = im.width, im.height, im.format
                        o = im.getexif().get(0x0112)
                        if o in (5, 6, 7, 8):
                            d["szer"], d["wys"] = d["wys"], d["szer"]
                except Exception:  # noqa: BLE001
                    pass
            elif r["rodzaj"] == "film":
                from . import filmy
                d.update(filmy.informacje(sc))
        if d["istnieje"] and r["rodzaj"] == "zdjecie":
            d.update(exif_szczegoly(sc))
        try:
            from . import twarze
            d["osoby"] = sorted({t["nazwa"] for t in twarze.twarze_pliku(self, id_)["twarze"] if t["nazwa"]})
        except Exception:  # noqa: BLE001
            d["osoby"] = []
        return d

    def pokaz_w_folderze(self, id_: int) -> dict:
        """📂 Eksplorator Windows z zaznaczonym plikiem (inne systemy: sam folder)."""
        sc = self.sciezka(id_, "film") or self.sciezka(id_, "zdjecie")
        if not sc or not os.path.exists(sc):
            return {"blad": "Pliku nie ma już w tym miejscu (odłączony dysk?)."}
        import subprocess
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", os.path.normpath(sc)])  # noqa: S603,S607
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(sc)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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


_ZIPY: dict[str, tuple[float, list[int]]] = {}  # klucz -> (czas, id) — lista z POST, pobranie zwykłym linkiem (GET)


def zip_klucz(ids: list[int]) -> dict:
    teraz = time.time()
    for k in [k for k, (t, _) in _ZIPY.items() if teraz - t > 3600]:
        _ZIPY.pop(k, None)
    k = secrets.token_urlsafe(12)
    _ZIPY[k] = (teraz, [int(i) for i in ids][:5000])
    return {"klucz": k, "n": len(_ZIPY[k][1])}


def wyslij_zip(h: BaseHTTPRequestHandler, sciezki: list[str], nazwa: str) -> None:
    """ZIP pakowany w locie (bez kompresji — zdjęcia i filmy są już skompresowane), od razu do przeglądarki."""
    import zipfile
    from urllib.parse import quote
    if not sciezki:
        h.send_response(HTTPStatus.NOT_FOUND)
        h.send_header("Content-Length", "0")
        h.end_headers()
        return
    nazwa = re.sub(r'[\\/:*?"<>|]+', "_", nazwa).strip() or "Zdjecia"
    h.send_response(HTTPStatus.OK)
    h.send_header("Content-Type", "application/zip")
    h.send_header("Content-Disposition", f"attachment; filename=\"zdjecia.zip\"; filename*=UTF-8''{quote(nazwa + '.zip')}")
    h.send_header("Cache-Control", "no-store")
    h.send_header("Connection", "close")
    h.end_headers()
    h.close_connection = True
    uzyte: set[str] = set()
    try:
        with zipfile.ZipFile(h.wfile, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
            for sc in sciezki:
                if not os.path.isfile(sc):
                    continue
                rdzen, rozsz = os.path.splitext(os.path.basename(sc))
                n, i = rdzen + rozsz, 2
                while n.lower() in uzyte:
                    n, i = f"{rdzen} ({i}){rozsz}", i + 1
                uzyte.add(n.lower())
                try:
                    z.write(sc, n)
                except OSError:
                    continue
    except (ConnectionError, OSError, ValueError):
        pass  # pobieranie przerwane w przeglądarce


_FILTR = threading.local()
_LISTY = ("/api/g/lata", "/api/g/pliki", "/api/g/szukaj", "/api/g/tego-dnia", "/api/g/kolekcja", "/api/g/mapa",
          "/api/g/osoba", "/api/g/foldery", "/api/g/folder", "/api/g/serie")  # filtr rodzaju na czas jednego zapytania (galeria jest wspólna dla okna i telefonu)


def biblioteka_pliku(sciezka: str) -> str | None:
    """Korzeń uporządkowanej biblioteki, w której leży plik (folder z „Zdjęcia/Zdjęcia z RRRR” albo
    „Dokumenty/Dokumenty z RRRR”) — albo None, gdy plik leży gdzie indziej."""
    czesci = re.split(r"[\\/]", os.path.abspath(sciezka))
    for i in range(len(czesci) - 2, 0, -1):
        a, b = czesci[i], czesci[i + 1] if i + 1 < len(czesci) else ""
        if (a in ("Zdjęcia", "Filmy") and re.fullmatch(rf"{a} z \d{{4}}", b)) or \
           (a == "Dokumenty" and (re.fullmatch(r"Dokumenty z \d{4}(?: \(.*\))?", b) or b == "Bez daty")):
            return os.sep.join(czesci[:i]) or os.sep
    return None


def folder_w_bibliotece(r: dict, dokument: bool) -> str | None:
    """Gdzie w uporządkowanej bibliotece powinien leżeć plik po zmianie typu (zdjęcie ⇄ dokument)."""
    from datetime import datetime

    from . import planista
    korzen = biblioteka_pliku(r["sciezka"])
    if not korzen:
        return None
    wzgl = os.path.relpath(r["sciezka"], korzen).replace("\\", "/")
    try:
        d = datetime.fromisoformat(r["data"][:19]) if r.get("data") else None
    except ValueError:
        d = None
    if dokument:
        if wzgl.startswith("Dokumenty/"):
            return None  # już w dokumentach
        return os.path.join(korzen, *planista.folder_dokumentow(r.get("data")).split("/"))
    if not wzgl.startswith("Dokumenty/"):
        return None  # już wśród zdjęć
    rok_dir = os.path.join(korzen, "Zdjęcia", f"Zdjęcia z {d.year}") if d else os.path.join(korzen, "Zdjęcia", "Bez daty")
    if not d:
        return rok_dir
    mies = planista.MIESIACE[d.month - 1]
    fraza = ""
    if r.get("lat") is not None:
        try:
            fraza = miejsca.fraza(miejsca.etykieta(r["lat"], r["lon"]))
        except Exception:  # noqa: BLE001
            fraza = ""
    try:  # istniejący folder tego miesiąca (np. „Kwiecień w domu”) — tam, gdzie reszta zdjęć z tego czasu
        juz = sorted(n for n in os.listdir(rok_dir) if (n == mies or n.startswith(mies + " ")) and os.path.isdir(os.path.join(rok_dir, n)))
    except OSError:
        juz = []
    wybor = next((n for n in juz if fraza and n == f"{mies} {fraza}"), None) or (juz[0] if len(juz) == 1 else None)
    return os.path.join(rok_dir, wybor or planista.czysta_nazwa(f"{mies} {fraza}".strip()))


def _znak_wodny(im, tekst: str):
    """Podpis w prawym dolnym rogu (półprzezroczysty, z cieniem) — np. „© Kowalscy 2024”."""
    from PIL import Image, ImageDraw, ImageFont
    rozm = max(14, im.width // 38)
    czcionka = None
    for n in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            czcionka = ImageFont.truetype(n, rozm)
            break
        except OSError:
            continue
    if czcionka is None:
        try:
            czcionka = ImageFont.load_default(size=rozm)
        except TypeError:  # starszy Pillow
            czcionka = ImageFont.load_default()
    warstwa = Image.new("RGBA", im.size, (0, 0, 0, 0))
    r = ImageDraw.Draw(warstwa)
    l, t, p, d = r.textbbox((0, 0), tekst, font=czcionka)
    m = rozm
    x, y = im.width - (p - l) - m, im.height - (d - t) - m
    r.text((x + 2, y + 2), tekst, font=czcionka, fill=(0, 0, 0, 120))
    r.text((x, y), tekst, font=czcionka, fill=(255, 255, 255, 190))
    return Image.alpha_composite(im.convert("RGBA"), warstwa).convert("RGB")


def _ulamek(v) -> float | None:
    try:
        return float(v[0]) / float(v[1]) if isinstance(v, tuple) else float(v)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def exif_szczegoly(sciezka: str) -> dict:
    """📷 Dane z aparatu (przysłona, czas, ISO, ogniskowa, obiektyw, lampa…) i histogram jasności / RGB."""
    from PIL import Image, ImageOps
    out: dict = {}
    try:
        with Image.open(sciezka) as im:
            ex = im.getexif()
            sz = ex.get_ifd(0x8769) if ex else {}
            f = _ulamek(sz.get(0x829D))
            t = _ulamek(sz.get(0x829A))
            iso = sz.get(0x8827)
            ogn = _ulamek(sz.get(0x920A))
            out["exif"] = {k: v for k, v in {
                "przyslona": f"f/{f:.1f}".replace(".0", "") if f else None,
                "czas": (f"1/{round(1 / t)} s" if t < 0.5 else f"{t:.1f} s".replace(".0 ", " ")) if t else None,
                "iso": int(iso[0] if isinstance(iso, tuple) else iso) if iso else None,
                "ogniskowa": (f"{ogn:.0f} mm" + (f" (≈ {sz.get(0xA405)} mm pełnej klatki)" if sz.get(0xA405) else "")) if ogn else None,
                "obiektyw": str(sz.get(0xA434) or "").strip("\x00 ") or None,
                "lampa": ("błysnęła" if int(sz.get(0x9209)) & 1 else "bez lampy") if sz.get(0x9209) is not None else None,
                "korekta": f"{_ulamek(sz.get(0x9204)):+.1f} EV" if _ulamek(sz.get(0x9204)) else None,
                "balans": {0: "automatyczny", 1: "ręczny"}.get(sz.get(0xA403)),
                "producent": str(ex.get(0x010F) or "").strip("\x00 ") or None,
                "model": str(ex.get(0x0110) or "").strip("\x00 ") or None,
                "program": str(ex.get(0x0131) or "").strip("\x00 ") or None,
            }.items() if v}
            try:
                im.draft("RGB", (256, 256))
            except Exception:  # noqa: BLE001
                pass
            m = ImageOps.exif_transpose(im).convert("RGB")
        m.thumbnail((256, 256))
        hist = m.histogram()  # 3 × 256
        jas = m.convert("L").histogram()
        do64 = lambda h: [sum(h[i:i + 4]) for i in range(0, 256, 4)]  # noqa: E731
        n = sum(jas) or 1
        out["histogram"] = {"r": do64(hist[:256]), "g": do64(hist[256:512]), "b": do64(hist[512:]), "l": do64(jas),
                            "ciemne": round(100 * sum(jas[:3]) / n, 1), "jasne": round(100 * sum(jas[253:]) / n, 1)}
    except Exception:  # noqa: BLE001 — uszkodzony / nieobsługiwany plik: bez szczegółów
        pass
    return out


def obsluz_api(g: Galeria, sciezka: str, q: dict, okno: bool = False):
    """/api/g/… -> (treść, typ) albo („film”, ścieżka) albo None, gdy to nie ścieżka galerii.
    `okno` — zapytanie z okna programu na komputerze (tam widać ukryte albumy); telefon/serwer 24/7 — nie."""
    _FILTR.okno = okno
    r = q.get("r", [""])[0]
    # filtr tylko dla list (oś czasu, mapa, szukanie…) — pojedynczy plik, miniatura, film zawsze bez filtra
    _FILTR.rodzaj = r if r in ("zdjecie", "film", "dokument") and sciezka in _LISTY else ""
    kol = q.get("kol", [""])[0]
    _FILTR.kolejnosc = kol if kol in ("nowe", "stare") and sciezka in _LISTY else ""
    ap = q["ap"][0][:120] if "ap" in q and (sciezka in _LISTY or sciezka == "/api/g/aparaty") else None
    _FILTR.aparat = "" if ap == "~" else ap  # „~” = zdjęcia bez nazwy aparatu (puste parametry giną po drodze)
    _FILTR.pora = q.get("pora", [""])[0] if sciezka in _LISTY or sciezka == "/api/g/aparaty" else ""
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
    if sciezka == "/api/g/miejsce":  # wyszukiwarka miejscowości do ustawiania lokalizacji (bez internetu: Polska)
        from . import miejsca
        w = miejsca.szukaj_miejsca(q.get("q", [""])[0][:100])
        return {"miejsca": [{"nazwa": n, "lat": la, "lon": lo} for la, lo, n in (w or {}).get("pl", [])[:8]]}, None
    if sciezka == "/api/g/tego-dnia":
        return g.tego_dnia(q.get("md", [""])[0], i("dni")), None
    if sciezka == "/api/g/albumy":
        return g.albumy(), None
    if sciezka == "/api/g/kolekcja":
        return g.kolekcja(q.get("typ", [""])[0], i("album"), i("od"), min(i("ile", 200), 500)), None
    if sciezka == "/api/g/mapa":
        return g.mapa(), None
    if sciezka == "/api/g/serie":
        return g.serie(i("od"), min(i("ile", 120), 500)), None
    if sciezka == "/api/g/seria":
        return g.seria(i("id")), None
    if sciezka == "/api/g/ostrosc":
        return g.ostrosc([int(x) for x in q.get("ids", [""])[0].split(",") if x.isdigit()]), None
    if sciezka == "/api/g/aparaty":
        return g.aparaty(), None
    if sciezka == "/api/g/foldery":
        return g.foldery(), None
    if sciezka == "/api/g/folder":
        return g.folder(q.get("f", [""])[0], bool(i("pod")), i("od"), min(i("ile", 200), 500)), None
    if sciezka in ("/api/g/osoby", "/api/g/twarz", "/api/g/twarze-pliku", "/api/g/osoba"):
        from . import twarze
        if sciezka == "/api/g/osoby":
            return twarze.osoby(g, bool(q.get("wszystkie"))), None
        if sciezka == "/api/g/twarz":
            return twarze.miniatura_twarzy(g, i("id")), "image/jpeg"
        if sciezka == "/api/g/twarze-pliku":
            return twarze.twarze_pliku(g, i("id")), None
        return g.osoba(i("id"), i("od"), min(i("ile", 200), 500)), None
    if sciezka == "/api/g/plik":
        return g.plik(i("id")) or {"blad": "nie ma takiego pliku"}, None
    if sciezka == "/api/g/wlasciwosci":
        return g.wlasciwosci(i("id")), None
    if sciezka == "/api/g/miniatura":
        return g.miniatura(i("id"), bool(q.get("srednia"))), "image/jpeg"
    if sciezka == "/api/g/podglad":
        return g.podglad(i("id")), "image/jpeg"
    if sciezka == "/api/g/film":
        return "film", g.sciezka(i("id"), "film")
    if sciezka == "/api/g/zip":
        if i("album"):
            return "zip", g.pliki_zip(album=i("album")), g.nazwa_albumu(i("album"))
        _, ids = _ZIPY.get(q.get("k", [""])[0], (0, []))
        return "zip", g.pliki_zip(ids), f"Zdjęcia ({len(ids)})"
    if sciezka == "/api/g/film-mp4":  # format, którego przeglądarka nie zna — przerabiany w locie (ffmpeg)
        return "film-mp4", g.sciezka(i("id"), "film"), max(0, i("od")), q.get("f", [""])[0] == "webm"
    return None


def obsluz_post(g: Galeria, sciezka: str, dane: dict) -> dict | None:
    """Zmiany kolekcji (ulubione, albumy) i miniatury filmów — tylko z okna programu (telefon jest tylko do odczytu)."""
    _FILTR.rodzaj = ""
    _FILTR.aparat, _FILTR.pora = None, ""
    _FILTR.okno = True
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
    if sciezka == "/api/g/pokaz-w-folderze":
        return g.pokaz_w_folderze(int(dane.get("id") or 0))
    if sciezka == "/api/g/zip":
        return zip_klucz(ids)
    if sciezka == "/api/g/album/udostepnij":
        return g.udostepnij(int(dane.get("album") or 0), bool(dane.get("wlacz", True)))
    if sciezka == "/api/g/przenies-z-powrotem":  # „Cofnij” po zmianie typu — dokładnie pod starą ścieżkę
        wyn = [g.przenies_plik(int(r.get("id") or 0), sciezka=str(r.get("z") or "")) for r in (dane.get("ruchy") or [])[:5000]
               if isinstance(r, dict)]
        return {"przeniesione": sum(1 for w in wyn if w.get("ok")), "bledy": [w["blad"] for w in wyn if w.get("blad")]}
    if sciezka == "/api/g/eksport":
        return g.eksportuj(int(dane.get("id") or 0), str(dane.get("cel") or ""), int(dane.get("bok") or 0),
                           int(dane.get("jakosc") or 88), bool(dane.get("bez_gps", True)), str(dane.get("znak") or ""))
    if sciezka == "/api/g/nazwy-podglad":
        return g.nazwy_podglad(ids[:5000], str(dane.get("wzor") or ""), int(dane.get("start") or 1))
    if sciezka == "/api/g/zmien-nazwe":
        return g.zmien_nazwe(int(dane.get("id") or 0), str(dane.get("nazwa") or ""))
    if sciezka == "/api/g/album/ukryj":
        return g.album_ukryj(int(dane.get("album") or 0), bool(dane.get("tak", True)))
    if sciezka == "/api/g/ukrywanie":
        return g.ustaw_ukrywanie(bool(dane.get("wlacz", True)))
    if sciezka.startswith(("/api/g/twarze/", "/api/g/osoba/", "/api/g/twarz/")):
        from . import twarze
        o = int(dane.get("id") or 0)
        if sciezka == "/api/g/twarze/start":
            powod = twarze.start(g)
            return {"blad": powod} if powod else {"ok": True, "stan": twarze.stan(g.baza)}
        if sciezka == "/api/g/twarze/przerwij":
            twarze.przerwij(g.baza)
            return {"ok": True}
        if sciezka == "/api/g/osoba/nazwa":
            return twarze.nazwij(g, o, str(dane.get("nazwa", "")))
        if sciezka == "/api/g/osoba/polacz":
            return twarze.polacz(g, ids)
        if sciezka == "/api/g/osoba/ukryj":
            return twarze.ukryj(g, o, bool(dane.get("tak", True)))
        if sciezka == "/api/g/twarz/odlacz":
            return twarze.odlacz(g, o)
        if sciezka == "/api/g/twarz/przypisz":
            return twarze.przypisz(g, o, int(dane.get("osoba") or 0))
    return obsluz_usuwanie(g, sciezka, dane)


ZMIANY_PLIKOW = ("/api/g/usun", "/api/g/usun/cofnij", "/api/g/lokalizacja", "/api/g/data", "/api/g/edytuj",
                 "/api/g/edytuj/cofnij", "/api/g/dokument", "/api/g/przenies-z-powrotem", "/api/g/zmien-nazwe")


def obsluz_usuwanie(g: Galeria, sciezka: str, dane: dict, okno: bool = True) -> dict | None:
    """🗑 Usuń / Cofnij, 📍 lokalizacja — w oknie programu i na telefonie (gdy pozwolono sterować z telefonu)."""
    _FILTR.rodzaj = ""  # zmiany dotyczą wskazanych plików — bez filtra widoku
    _FILTR.aparat, _FILTR.pora = None, ""
    _FILTR.okno = okno
    if sciezka == "/api/g/usun":
        return g.usun([int(x) for x in (dane.get("ids") or []) if str(x).isdigit()])
    if sciezka == "/api/g/usun/cofnij":
        return g.cofnij_usuniecie(int(dane.get("partia") or 0))
    if sciezka == "/api/g/data":
        return g.data([int(x) for x in (dane.get("ids") or []) if str(x).isdigit()], str(dane.get("data") or ""))
    if sciezka == "/api/g/dokument":
        return g.dokument([int(x) for x in (dane.get("ids") or []) if str(x).isdigit()], bool(dane.get("tak", True)),
                          bool(dane.get("przenies", True)))
    if sciezka == "/api/g/edytuj":
        op = dane.get("op") if isinstance(dane.get("op"), dict) else {}
        return g.edytuj(int(dane.get("id") or 0), op, bool(dane.get("zastap")))
    if sciezka == "/api/g/edytuj/cofnij":
        return g.edytuj_cofnij(int(dane.get("id") or 0), int(dane.get("partia") or 0) or None)
    if sciezka == "/api/g/lokalizacja":
        return g.lokalizacja([int(x) for x in (dane.get("ids") or []) if str(x).isdigit()],
                             dane.get("lat"), dane.get("lon"))
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


class _Kawalki:
    """Najwyżej `n` bajtów ze strumienia — ciało zapytania przekazywane dalej bez wczytywania całości."""

    def __init__(self, f, n: int):
        self.f, self.zostalo = f, n

    def read(self, ile: int = -1) -> bytes:
        if self.zostalo <= 0:
            return b""
        k = self.f.read(self.zostalo if ile is None or ile < 0 else min(ile, self.zostalo))
        self.zostalo -= len(k)
        return k


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

            def _znany(self, t) -> bool:
                return bool(t) and (t in s.tokeny or bool(s.staly_token) and secrets.compare_digest(t, s.staly_token))

            def _sesja(self) -> str:
                """Ciasteczko sesji z logowania PIN-em — pełny program przez przeglądarkę telefonu (obrazki, filmy)."""
                for k in (self.headers.get("Cookie") or "").split(";"):
                    nazwa, _, wart = k.strip().partition("=")
                    if nazwa == "kat_s":
                        return wart
                return ""

            def _ok(self, q) -> bool:
                return (self._znany(self.headers.get("X-Token") or q.get("t", [""])[0]) or
                        self._znany(self._sesja()))

            def _ciasteczko(self, t: str) -> None:
                self.send_header("Set-Cookie", f"kat_s={t}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000")

            def _przekieruj(self, dokad: str, t: str | None = None) -> None:
                self.send_response(HTTPStatus.SEE_OTHER)
                if t:
                    self._ciasteczko(t)
                self.send_header("Location", dokad)
                self.send_header("Content-Length", "0")
                self.end_headers()

            # --- 🖥 pełny program z telefonu: zapytania przekazywane do programu na komputerze -------------
            ZABRONIONE = ("/api/zamknij", "/api/aktualizacja/instaluj")  # nie z telefonu

            def _pelny(self):
                return s.pilot.pelny() if s.pilot is not None else None

            def _przekaz(self, sciezka_glowna: str | None = None) -> None:
                import http.client
                from urllib.parse import urlencode
                cel = self._pelny()
                if not cel:
                    return self._wyslij({"blad": "Pełny program z telefonu jest wyłączony — na komputerze: 📱 → "
                                                 "„Pozwól sterować z telefonu”."}, kod=HTTPStatus.FORBIDDEN)
                port, token = cel
                u = urlparse(self.path)
                if u.path in self.ZABRONIONE:
                    return self._wyslij({"blad": "Tego nie da się zrobić z telefonu."}, kod=HTTPStatus.FORBIDDEN)
                q = parse_qs(u.query, keep_blank_values=True)
                q["t"] = [token]
                adres = (sciezka_glowna or u.path) + "?" + urlencode(q, doseq=True)
                n = int(self.headers.get("Content-Length") or 0)
                # duże wysyłki (📤 filmy z telefonu) — przekazywane kawałkami, bez trzymania w pamięci
                tresc = (_Kawalki(self.rfile, n) if n > 8 * 1024 * 1024 else self.rfile.read(n)) if n else None
                naglowki = {"X-Token": token, "X-Z-Telefonu": "1"}  # program wie, że to telefon (ukryte albumy)
                if n:
                    naglowki["Content-Length"] = str(n)
                for k in ("Content-Type", "Range"):
                    if self.headers.get(k):
                        naglowki[k] = self.headers[k]
                pol = http.client.HTTPConnection("127.0.0.1", port, timeout=900)
                try:
                    pol.request(self.command, adres, body=tresc, headers=naglowki)
                    r = pol.getresponse()
                    self.send_response(r.status)
                    dlugosc = r.getheader("Content-Length")
                    for k in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges", "Cache-Control",
                              "Content-Disposition"):
                        if r.getheader(k):
                            self.send_header(k, r.getheader(k))
                    if not dlugosc:
                        self.send_header("Connection", "close")
                        self.close_connection = True
                    self.end_headers()
                    while True:
                        kawalek = r.read(64 * 1024)
                        if not kawalek:
                            break
                        self.wfile.write(kawalek)
                except (OSError, http.client.HTTPException):
                    pass  # telefon zamknął połączenie / program na komputerze zamknięty
                finally:
                    pol.close()

            def _album(self, u, q):
                """🔗 Udostępniony album: /a/<token>[/api|min|pod|film|oryg|zip] — bez PIN-u, tylko ten album."""
                _FILTR.rodzaj = _FILTR.kolejnosc = ""
                cz = u.path.split("/")
                token, co = cz[2] if len(cz) > 2 else "", cz[3] if len(cz) > 3 else ""
                galerie = [s.galerie("wszystko"), s.galerie("przegladarka")] if s.galerie is not None else [s.galeria]
                g = album = None
                for kand in galerie:
                    album = kand.album_tokenu(token)
                    if album:
                        g = kand
                        break
                if not album:
                    return self._wyslij("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                                        "<body style='font:16px system-ui;padding:30px;text-align:center'>"
                                        "<h2>🔗 Ten link już nie działa</h2><p>Album nie jest już udostępniany.</p>",
                                        "text/html; charset=utf-8", HTTPStatus.NOT_FOUND)
                if co == "":
                    return self._wyslij((UI / "album.html").read_bytes(), "text/html; charset=utf-8")
                if co == "api":
                    k = g.kolekcja("album", album, 0, 5000)
                    return self._wyslij({"nazwa": k.get("nazwa"), "pliki": k.get("pliki", [])})
                if co == "zip":
                    return wyslij_zip(self, g.pliki_zip(album=album), g.nazwa_albumu(album))
                try:
                    id_ = int(q.get("id", ["0"])[0])
                except ValueError:
                    id_ = 0
                if not g.w_albumie(album, id_):
                    return self._wyslij(None)
                if co == "min":
                    return self._wyslij(g.miniatura(id_, bool(q.get("s"))), "image/jpeg")
                if co == "pod":
                    return self._wyslij(g.podglad(id_), "image/jpeg")
                if co == "film":
                    return wyslij_strumien(self, g.sciezka(id_, "film"))
                if co == "oryg":
                    sc = g.sciezka(id_, "zdjecie")
                    if not sc or not os.path.isfile(sc):
                        return self._wyslij(None)
                    from urllib.parse import quote
                    with open(sc, "rb") as f:
                        dane = f.read()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(os.path.basename(sc))}")
                    self.send_header("Content-Length", str(len(dane)))
                    self.end_headers()
                    self.wfile.write(dane)
                    return None
                return self._wyslij(None)

            def do_GET(self):
                u = urlparse(self.path)
                q = parse_qs(u.query)
                if u.path.startswith("/a/"):
                    return self._album(u, q)
                if u.path == "/program":  # 🖥 pełny program (duplikaty, dokumenty, drzewo…) — po PIN-ie
                    t = q.get("s", [""])[0]
                    if self._znany(t):
                        return self._przekieruj("/program", t)  # ciasteczko sesji z tokenu pilota
                    if not self._znany(self._sesja()):
                        return self._przekieruj("/?dalej=/program")
                    return self._przekaz("/")
                if (s.pilot is not None and u.path not in ("/", "/galeria") and not u.path.startswith(("/ui/", "/api/g/"))
                        and u.path != "/api/pilot"):
                    if not self._ok(q):
                        return self._wyslij({"blad": "Podaj PIN"}, kod=HTTPStatus.UNAUTHORIZED)
                    return self._przekaz()
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
                if w[0] == "film-mp4":
                    from . import filmy
                    return filmy.wyslij_mp4(self, w[1], w[2], w[3])
                if w[0] == "zip":
                    return wyslij_zip(self, w[1], w[2])
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
                if u.path == "/api/g/zip":  # tylko odczyt — także bez sterowania
                    if not self._ok(parse_qs(u.query)):
                        return self._wyslij({"blad": "Podaj PIN"}, kod=HTTPStatus.UNAUTHORIZED)
                    try:
                        n = int(self.headers.get("Content-Length") or 0)
                        dane = json.loads(self.rfile.read(min(n, 200000)) or b"{}")
                    except ValueError:
                        dane = {}
                    ids = [int(x) for x in (dane.get("ids") or []) if str(x).isdigit()] if isinstance(dane, dict) else []
                    return self._wyslij(zip_klucz(ids))
                if u.path in ZMIANY_PLIKOW and s.pilot is not None:
                    q = parse_qs(u.query)
                    if not self._ok(q):
                        return self._wyslij({"blad": "Podaj PIN"}, kod=HTTPStatus.UNAUTHORIZED)
                    if not s.pilot.sterowanie:
                        return self._wyslij({"blad": "Zmiany z telefonu są wyłączone — włącz sterowanie "
                                                     "na komputerze (📱)."}, kod=HTTPStatus.FORBIDDEN)
                    blad = s.pilot.zajety_projekt(q.get("z", [""])[0])
                    if blad:
                        return self._wyslij({"blad": blad}, kod=HTTPStatus.CONFLICT)
                    try:
                        n = int(self.headers.get("Content-Length") or 0)
                        dane = json.loads(self.rfile.read(min(n, 200000)) or b"{}")
                    except ValueError:
                        dane = {}
                    z = q.get("z", [""])[0]
                    g = s.galerie(z) if s.galerie is not None and z in s.ZAKRESY else s.galeria
                    w = obsluz_usuwanie(g, u.path, dane if isinstance(dane, dict) else {}, okno=False)
                    s.pilot.po_usunieciu(z, w, u.path)
                    return self._wyslij(w, kod=HTTPStatus.BAD_REQUEST if "blad" in w else HTTPStatus.OK)
                if u.path != "/api/g/zaloguj":
                    if s.pilot is not None and self._ok(parse_qs(u.query)):
                        return self._przekaz()  # pełny program: zapisy, decyzje, odkładanie…
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
                    dane = json.dumps({"t": t}).encode()
                    self.send_response(HTTPStatus.OK)
                    self._ciasteczko(t)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(dane)))
                    self.end_headers()
                    self.wfile.write(dane)
                    return
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
