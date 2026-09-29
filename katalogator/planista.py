"""Propozycja drzewa folderów (plan) i jego edycja z cofaniem.

Plan to tabela `plan`: dla każdego pliku ze źródeł — ścieżka w miejscu docelowym (`cel`,
względna, z „/”), tryb (kopiuj/przenies) i stan. Pliki, które już są w miejscu docelowym,
wchodzą do planu jako „istniejacy” (nie da się ich edytować — pokazują wynikowe drzewo).
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import PurePath

from . import analiza, duplikaty, dyski, kategorie, miejsca

SCHEMAT = """
CREATE TABLE IF NOT EXISTS plan (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    plik_id   INTEGER,
    sciezka   TEXT NOT NULL,
    rodzaj    TEXT NOT NULL,
    rozmiar   INTEGER NOT NULL,
    data      TEXT,
    cel       TEXT NOT NULL,
    tryb      TEXT NOT NULL,
    stan      TEXT NOT NULL,
    pominiety INTEGER NOT NULL DEFAULT 0,
    uwaga     TEXT,
    wynik     TEXT
);
CREATE INDEX IF NOT EXISTS ix_plan_cel ON plan(cel);
CREATE TABLE IF NOT EXISTS plan_meta (klucz TEXT PRIMARY KEY, wartosc TEXT);
CREATE TABLE IF NOT EXISTS plan_ops (
    op INTEGER PRIMARY KEY AUTOINCREMENT, opis TEXT NOT NULL, czas REAL NOT NULL, cofnieta INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS plan_zmiany (
    op INTEGER NOT NULL, id INTEGER NOT NULL, stary_cel TEXT, stary_pom INTEGER, nowy_cel TEXT, nowy_pom INTEGER
);
"""

MIESIACE = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", "Lipiec", "Sierpień", "Wrzesień",
            "Październik", "Listopad", "Grudzień"]
RANGA_DATY = {"exif": 0, "film": 1, "nazwa": 2, "plik": 3, None: 4}
PRZERWA_WYJAZDU = timedelta(hours=48)
MARGINES_WYJAZDU = timedelta(hours=6)
_NAGRANIE = re.compile(r"^(vid|pxl|img|mov|mvi|dsc|gopr|gh\d|dji|wp_|video|signal|screen)|(19|20)\d{6}", re.I)
_ZLE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
DOKUMENTY = "Dokumenty"


def folder_dokumentow(data: str | None) -> str:
    """Dokumenty sortowane po latach, bez dalszych podfolderów: Dokumenty/Dokumenty z 2023."""
    d = _dt(data)
    return f"{DOKUMENTY}/{DOKUMENTY} z {d.year}" if d else f"{DOKUMENTY}/Bez daty"


def folder_smieci(p: dict) -> str:
    """Odłożone/Śmieci/<nazwa folderu, z którego pochodzi plik>."""
    nad = os.path.basename(os.path.dirname(p["sciezka"]))
    return kategorie.SMIECI + ("/" + czysta_nazwa(nad) if nad and not re.fullmatch(r"[A-Za-z]:?", nad) else "")


_UWAGA_PODEJRZANE = re.compile(r";?\s*nie z aparatu\? \([^)]*\) — zdecyduj w zakładce „Nie z aparatu”")


def przygotuj(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMAT)
    kol = {r[1] for r in db.execute("PRAGMA table_info(plan_zmiany)")}
    if "stara_data" not in kol:  # baza z wersji 1.0
        db.execute("ALTER TABLE plan_zmiany ADD COLUMN stara_data TEXT")
        db.execute("ALTER TABLE plan_zmiany ADD COLUMN nowa_data TEXT")
    kol = {r[1] for r in db.execute("PRAGMA table_info(plan)")}
    if "alt" not in kol:  # od 1.4: miejsce „jako zwykłe zdjęcie” i kategoria (śmieci / nie z aparatu)
        db.execute("ALTER TABLE plan ADD COLUMN alt TEXT")
        db.execute("ALTER TABLE plan ADD COLUMN kat TEXT")
    duplikaty.przygotuj(db)
    analiza.przygotuj(db)
    kategorie.przygotuj(db)


def czysta_nazwa(n: str, zapas: str = "_") -> str:
    """Nazwa folderu bez znaków niedozwolonych w Windows, bez kropek/spacji na końcu."""
    n = _ZLE.sub("_", str(n or "")).strip().rstrip(". ")
    return n[:120] or zapas


def czysta_sciezka(s: str) -> str:
    cz = [czysta_nazwa(c) for c in re.split(r"[\\/]+", s or "") if c.strip() and c.strip() not in (".", "..")]
    return "/".join(cz)


def _rel(sciezka: str, korzen: str) -> str:
    return os.path.relpath(sciezka, korzen).replace("\\", "/")


def _dt(iso: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(iso) if iso else None
    except ValueError:
        return None


# --- generowanie propozycji ---------------------------------------------------------

def generuj(db: sqlite3.Connection, zrodla: list[dict], cel: str, postep=None, przerwij=None,
            dom: str | None = None) -> dict:
    """dom: nazwa miejscowości zamieszkania (np. „Olkusz”) — gdy pusta, wykrywana z najczęstszego miejsca."""
    przygotuj(db)
    if not cel:
        raise ValueError("Najpierw wybierz miejsce docelowe.")
    cel = os.path.normpath(cel)
    zrodla = dyski.normalizuj_wybor(zrodla)
    pliki = [dict(r) for r in db.execute("SELECT rowid id, * FROM pliki")]
    istniejace, zrodlowe = [], []
    for p in pliki:
        if dyski.zawiera(cel, p["sciezka"]):
            istniejace.append(p)
            continue
        z = next((z for z in zrodla if dyski.zawiera(z["sciezka"], p["sciezka"])), None)
        if z:
            p["tryb"], p["zrodlo"] = z["tryb"], z["sciezka"]
            zrodlowe.append(p)
    if postep:
        postep("pliki już w miejscu docelowym", 0, 0, 0)
    _odciski_dla_celu(db, zrodlowe, istniejace, przerwij)

    dokumenty = analiza.dokumenty_potwierdzone(db)
    decyzje = kategorie.decyzje(db)
    wym = kategorie.wymiary(db)
    wpisy: list[dict] = []
    for p in istniejace:
        wpisy.append({"p": p, "cel": _rel(p["sciezka"], cel), "tryb": "istniejacy", "stan": "istniejacy", "uwaga": None})

    # pliki towarzyszące (xmp, srt, RAW obok JPG) idą za plikiem głównym
    grupy = defaultdict(list)
    for p in zrodlowe:
        grupy[(os.path.dirname(p["sciezka"]).lower(), _rdzen(os.path.basename(p["sciezka"])))].append(p)
    prowadzacy: dict[int, dict] = {}
    for g in grupy.values():
        if len(g) > 1:
            glowny = min(g, key=lambda p: (p["rodzaj"] not in ("zdjecie", "film"), RANGA_DATY.get(p["zrodlo_daty"], 4),
                                           p["lat"] is None, -p["rozmiar"]))
            for p in g:
                if p is not glowny:
                    prowadzacy[p["id"]] = glowny

    media = [p for p in zrodlowe if p["id"] not in prowadzacy
             and (p["rodzaj"] == "zdjecie" or (p["rodzaj"] == "film" and _wlasne_nagranie(p)))]
    etykiety, dom = _etykiety_miejsc(media, dom)

    folder: dict[int, str] = {}
    uwagi: dict[int, str | None] = {}
    alt: dict[int, str] = {}      # gdzie trafiłby jako zwykłe zdjęcie (gdy zmienisz zdanie)
    kat: dict[int, str] = {}
    for p in zrodlowe:
        if p["id"] in prowadzacy:
            continue
        uw = []
        if p["id"] in etykiety:
            d = _dt(p["data"]) or datetime.fromtimestamp(p["mtime"])
            fr, uw_m = etykiety[p["id"]]
            rodz = "Zdjęcia" if p["rodzaj"] == "zdjecie" else "Filmy"
            f = f"{rodz}/{rodz} z {d.year}/{czysta_nazwa(f'{MIESIACE[d.month - 1]} {fr}'.strip())}"
            if uw_m:
                uw.append(uw_m)
            if p["zrodlo_daty"] == "plik":
                uw.append("data z pliku — sprawdź")
        elif p["rodzaj"] == "film":
            f = "Filmy/Inne/" + _prefiks_zrodla(p)
        elif p["rodzaj"] == "muzyka":
            f = "Muzyka/" + czysta_nazwa(p["wykonawca"] or "Nieznany wykonawca") + "/" + \
                czysta_nazwa(p["album"] or "Nieznany album")
            if not p["wykonawca"] or not p["album"]:
                uw.append("brak tagów")
        else:
            f = _prefiks_zrodla(p)
        alt[p["id"]] = f.strip("/")
        # kategorie: decyzja użytkownika > potwierdzony dokument > automatyczne śmieci > podejrzane
        d_uz = decyzje.get(p["sciezka"])
        w = wym.get(p["sciezka"])
        powod_s = kategorie.smieci(p, w)
        if d_uz == "smieci" or (powod_s and d_uz is None):
            f, uw = folder_smieci(p), [f"śmieci: {powod_s}" if powod_s else "śmieci (Twoja decyzja)"]
            kat[p["id"]] = "smieci"
        elif d_uz == "dokument" or (p["sciezka"] in dokumenty and d_uz != "zdjecie"):
            f, uw = folder_dokumentow(p["data"]), []
            kat[p["id"]] = "dokument"
        elif d_uz is None:
            powod_p = kategorie.podejrzane(p, w)
            if powod_p:
                uw.append(f"nie z aparatu? ({powod_p}) — zdecyduj w zakładce „Nie z aparatu”")
                kat[p["id"]] = "podejrzane"
        folder[p["id"]] = f.strip("/")
        uwagi[p["id"]] = "; ".join(uw) or None
    for p in zrodlowe:
        if p["id"] in prowadzacy:
            g = prowadzacy[p["id"]]
            while g["id"] in prowadzacy:
                g = prowadzacy[g["id"]]
            folder[p["id"]] = folder[g["id"]]
            alt[p["id"]] = alt.get(g["id"], folder[g["id"]])
            if g["id"] in kat:
                kat[p["id"]] = kat[g["id"]]
            uwagi[p["id"]] = f"razem z {os.path.basename(g['sciezka'])}"

    # identyczne pliki: już obecne w celu / powtórzone w źródłach
    hash_pliku = {r["sciezka"]: r["pelny"] for r in db.execute(
        "SELECT o.sciezka, o.pelny FROM odciski o JOIN pliki p ON p.sciezka=o.sciezka AND p.rozmiar=o.rozmiar "
        "AND p.mtime=o.mtime WHERE o.pelny IS NOT NULL")}
    w_celu = {}
    for p in istniejace:
        h = hash_pliku.get(p["sciezka"])
        if h:
            w_celu.setdefault(h, _rel(p["sciezka"], cel))
    cele_zrodel = {z["sciezka"] for z in zrodla}
    widziane: dict[str, dict] = {}
    for p in sorted(zrodlowe, key=lambda p: duplikaty._ocena(
            {"wzgledna": p["wzgledna"], "korzen": p["korzen"], "mtime": p["mtime"]}, cele_zrodel)):
        h = hash_pliku.get(p["sciezka"])
        stan, uw = "nowy", uwagi.get(p["id"])
        if h and h in w_celu:
            stan, uw = "juz_jest", f"już jest: {w_celu[h]}"
        elif h and h in widziane:
            stan, uw = "duplikat", f"kopia pliku {widziane[h]['wzgledna']}"
        elif h:
            widziane[h] = p
        nazwa = czysta_nazwa(os.path.basename(p["sciezka"]))
        wpisy.append({"p": p, "cel": folder[p["id"]] + "/" + nazwa, "alt": alt.get(p["id"], folder[p["id"]]) + "/" + nazwa,
                      "kat": kat.get(p["id"]), "tryb": p["tryb"], "stan": stan, "uwaga": uw})

    _rozwiaz_kolizje(wpisy)
    db.execute("DELETE FROM plan")
    db.execute("DELETE FROM plan_ops")
    db.execute("DELETE FROM plan_zmiany")
    db.executemany(
        "INSERT INTO plan(plik_id, sciezka, rodzaj, rozmiar, data, cel, tryb, stan, pominiety, uwaga, alt, kat) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [(w["p"]["id"], w["p"]["sciezka"], w["p"]["rodzaj"], w["p"]["rozmiar"], w["p"]["data"], w["cel"], w["tryb"],
          w["stan"], 1 if w["stan"] in ("juz_jest", "duplikat") else 0, w["uwaga"], w.get("alt"), w.get("kat"))
         for w in wpisy])
    db.execute("DELETE FROM plan_meta")
    db.executemany("INSERT INTO plan_meta VALUES (?,?)",
                   [("cel", cel), ("utworzono", str(time.time())), ("dom", dom or "")])
    db.commit()
    return podsumowanie(db)


def _rdzen(nazwa: str) -> str:
    """Wspólny rdzeń pliku i jego towarzyszy: IMG_1.jpg, IMG_1.xmp, IMG_1.jpg.json,
    IMG_1.jpg.supplemental-metadata.json (Google Zdjęcia) -> „img_1”."""
    n = nazwa.lower()
    for kon in (".json", ".xmp"):
        if n.endswith(kon) and n.count(".") > 1:
            n = n[: -len(kon)]
            if n.endswith(".supplemental-metadata"):
                n = n[: -len(".supplemental-metadata")]
            break
    return PurePath(n).stem


def _prefiks_zrodla(p: dict) -> str:
    """Ścieżka folderu dla „pozostałych” plików: nazwa wybranego folderu + podfoldery."""
    baza = os.path.basename(os.path.normpath(p["zrodlo"]).rstrip("\\/"))
    rel = os.path.dirname(_rel(p["sciezka"], p["zrodlo"]))
    cz = [czysta_nazwa(baza)] if baza and not re.fullmatch(r"[A-Za-z]:?", baza) else []
    return "/".join(cz + ([czysta_sciezka(rel)] if rel else [])).strip("/") or "Pozostałe"


def _wlasne_nagranie(p: dict) -> bool:
    return p["lat"] is not None or p["zrodlo_daty"] == "nazwa" or bool(_NAGRANIE.search(os.path.basename(p["sciezka"])))


def _etykiety_miejsc(media: list[dict], dom_wymuszony: str | None = None
                    ) -> tuple[dict[int, tuple[str, str | None]], str | None]:
    """Dla każdego zdjęcia/filmu: (fraza miejsca, uwaga). Wykrywa dom i wyjazdy."""
    for p in media:
        p["_dt"] = _dt(p["data"]) or datetime.fromtimestamp(p["mtime"])
        p["_m"] = miejsca.etykieta(p["lat"], p["lon"]) if p["lat"] is not None else None
    z_gps = sorted((p for p in media if p["_m"]), key=lambda p: p["_dt"])
    licz = Counter(p["_m"] for p in z_gps)
    dom = (dom_wymuszony or "").strip() or (licz.most_common(1)[0][0] if licz else None)

    # wyjazdy: kolejne zdjęcia poza domem, bez przerwy dłuższej niż 48 h
    wyjazdy: list[dict] = []
    for p in z_gps:
        if p["_m"] == dom:
            continue
        if wyjazdy and p["_dt"] - wyjazdy[-1]["koniec"] <= PRZERWA_WYJAZDU:
            w = wyjazdy[-1]
        else:
            w = {"start": p["_dt"], "koniec": p["_dt"], "licz": Counter()}
            wyjazdy.append(w)
        w["koniec"] = p["_dt"]
        w["licz"][p["_m"]] += 1
        p["_w"] = w
    # zdjęcia z domu przerywające wyjazd dzielą go (np. powrót na weekend)
    for w in wyjazdy:
        w["etykieta"] = w["licz"].most_common(1)[0][0]

    wynik = {}
    for p in media:
        if p["_m"]:
            m = p["_w"]["etykieta"] if p["_m"] != dom else dom
            uw = None
        else:
            w = next((w for w in wyjazdy if w["start"] - MARGINES_WYJAZDU <= p["_dt"] <= w["koniec"] + MARGINES_WYJAZDU),
                     None)
            z_folderu = None if w else miejsca.z_folderu(p.get("wzgledna") or "")
            if w:
                m, uw = w["etykieta"], "bez GPS — dopasowano do wyjazdu"
            elif z_folderu:
                m, uw = z_folderu, "bez GPS — miejsce z nazwy folderu"
            else:
                m, uw = dom, ("bez GPS" if dom else None)
        if m is None:
            fr = ""
        elif m == dom:
            fr = "w domu"
        else:
            fr = miejsca.fraza(m)
        wynik[p["id"]] = (fr, uw)
    return wynik, dom


def _odciski_dla_celu(db, zrodlowe: list[dict], istniejace: list[dict], przerwij) -> None:
    """Liczy pełne odciski tylko tam, gdzie plik ze źródła ma rozmiar jak plik w celu."""
    rozmiary = {p["rozmiar"] for p in istniejace}
    kandydaci = [p for p in zrodlowe if p["rozmiar"] in rozmiary] + [p for p in istniejace]
    kandydaci = [p for p in kandydaci if p["rozmiar"] in rozmiary and p["rozmiar"] > 0]
    znane = {r["sciezka"] for r in db.execute(
        "SELECT o.sciezka FROM odciski o JOIN pliki p ON p.sciezka=o.sciezka AND p.rozmiar=o.rozmiar AND p.mtime=o.mtime "
        "WHERE o.pelny IS NOT NULL")}
    for p in kandydaci:
        if p["sciezka"] in znane:
            continue
        if przerwij is not None and przerwij.is_set():
            from .skaner import Przerwano
            raise Przerwano(p["sciezka"])
        try:
            h = duplikaty._odcisk(p["sciezka"], p["rozmiar"], True, przerwij)
        except OSError:
            continue
        db.execute("INSERT OR REPLACE INTO odciski(sciezka, rozmiar, mtime, szybki, pelny) VALUES (?,?,?,NULL,?)",
                   (p["sciezka"], p["rozmiar"], p["mtime"], h))
    db.commit()


def _klucz(cel: str) -> str:
    return cel.lower()


def _rozwiaz_kolizje(wpisy: list[dict]) -> None:
    zajete = {_klucz(w["cel"]) for w in wpisy if w["tryb"] == "istniejacy"}
    for w in wpisy:
        if w["tryb"] == "istniejacy" or w["stan"] != "nowy":
            continue
        w["cel"] = _wolna_nazwa(w["cel"], zajete)
        zajete.add(_klucz(w["cel"]))


def _wolna_nazwa(cel: str, zajete: set[str]) -> str:
    if _klucz(cel) not in zajete:
        return cel
    folder, nazwa = cel.rsplit("/", 1) if "/" in cel else ("", cel)
    baza, ext = os.path.splitext(nazwa)
    i = 2
    while True:
        k = f"{folder}/{baza} ({i}){ext}" if folder else f"{baza} ({i}){ext}"
        if _klucz(k) not in zajete:
            return k
        i += 1


# --- odczyt ------------------------------------------------------------------------

def istnieje(db: sqlite3.Connection) -> bool:
    przygotuj(db)
    return db.execute("SELECT 1 FROM plan LIMIT 1").fetchone() is not None


def meta(db: sqlite3.Connection) -> dict:
    przygotuj(db)
    return {k: v for k, v in db.execute("SELECT klucz, wartosc FROM plan_meta")}


def podsumowanie(db: sqlite3.Connection) -> dict:
    przygotuj(db)
    r = db.execute(
        """SELECT
             SUM(tryb='kopiuj' AND pominiety=0 AND stan='nowy' AND wynik IS NULL) kopiuj,
             SUM(CASE WHEN tryb='kopiuj' AND pominiety=0 AND stan='nowy' AND wynik IS NULL THEN rozmiar END) kopiuj_b,
             SUM(tryb='przenies' AND pominiety=0 AND stan='nowy' AND wynik IS NULL) przenies,
             SUM(CASE WHEN tryb='przenies' AND pominiety=0 AND stan='nowy' AND wynik IS NULL THEN rozmiar END) przenies_b,
             SUM(tryb='istniejacy') istniejace, SUM(pominiety=1 AND tryb!='istniejacy') pominiete,
             SUM(uwaga IS NOT NULL AND tryb!='istniejacy' AND pominiety=0) uwagi,
             SUM(wynik='ok') zrobione, SUM(wynik LIKE 'blad%') bledy
           FROM plan""").fetchone()
    d = {k: (r[k] or 0) for k in r.keys()}
    m = meta(db)
    d["cel"] = m.get("cel", "")
    d["dom"] = m.get("dom", "")
    d["cofnij"] = _ostatnia_op(db, 0)
    d["ponow"] = _ostatnia_op(db, 1)
    return d


def drzewo(db: sqlite3.Connection) -> list[dict]:
    """Foldery z bezpośrednią zawartością i licznikami; klient składa hierarchię."""
    przygotuj(db)
    agr: dict[str, dict] = {}
    kolizje = Counter(_klucz(r[0]) for r in db.execute("SELECT cel FROM plan WHERE pominiety=0"))
    for r in db.execute("SELECT cel, tryb, stan, pominiety, uwaga, rozmiar, wynik FROM plan"):
        f = r["cel"].rsplit("/", 1)[0] if "/" in r["cel"] else ""
        a = agr.setdefault(f, {"sciezka": f, "nowe": 0, "istniejace": 0, "pominiete": 0, "uwagi": 0,
                               "konflikty": 0, "rozmiar": 0, "zrobione": 0})
        if r["tryb"] == "istniejacy":
            a["istniejace"] += 1
        elif r["pominiety"]:
            a["pominiete"] += 1
        else:
            a["nowe"] += 1
            a["rozmiar"] += r["rozmiar"]
            if r["uwaga"]:
                a["uwagi"] += 1
            if kolizje[_klucz(r["cel"])] > 1:
                a["konflikty"] += 1
            if r["wynik"] == "ok":
                a["zrobione"] += 1
    return sorted(agr.values(), key=lambda a: a["sciezka"].lower())


def pliki_folderu(db: sqlite3.Connection, folder: str, od: int = 0, ile: int = 200) -> dict:
    przygotuj(db)
    folder = folder.strip("/")
    wz = "cel LIKE ? ESCAPE '\\' AND instr(substr(cel, ?), '/') = 0"
    arg = [_like(folder + "/") + "%" if folder else "%", len(folder) + 2 if folder else 1]
    n = db.execute(f"SELECT COUNT(*) FROM plan WHERE {wz}", arg).fetchone()[0]
    wiersze = [dict(r) for r in db.execute(
        f"""SELECT id, plik_id, sciezka, rodzaj, rozmiar, data, cel, tryb, stan, pominiety, uwaga, wynik
            FROM plan WHERE {wz} ORDER BY tryb='istniejacy', data, cel LIMIT ? OFFSET ?""", [*arg, ile, od])]
    for w in wiersze:
        w["nazwa"] = w["cel"].rsplit("/", 1)[-1]
    return {"folder": folder, "razem": n, "pliki": wiersze}


def _like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# --- edycja z historią --------------------------------------------------------------

def _ostatnia_op(db, cofnieta: int) -> dict | None:
    r = db.execute("SELECT op, opis FROM plan_ops WHERE cofnieta=? ORDER BY op " + ("DESC" if not cofnieta else "ASC")
                   + " LIMIT 1", (cofnieta,)).fetchone()
    return dict(r) if r else None


def _zastosuj(db, opis: str, zmiany: list[tuple]) -> dict:
    """zmiany: [(id, nowy_cel, nowy_pom[, nowa_data])] — zapisuje historię, kasuje możliwość „ponów”."""
    stare = {r["id"]: r for r in db.execute(
        f"SELECT id, cel, pominiety, data FROM plan WHERE id IN ({','.join('?' * len(zmiany))}) "
        f"AND tryb != 'istniejacy'", [z[0] for z in zmiany])} if zmiany else {}
    pelne = []
    for z in zmiany:
        if z[0] not in stare:
            continue
        st = stare[z[0]]
        nowa_data = z[3] if len(z) > 3 else st["data"]
        if (st["cel"], st["pominiety"], st["data"]) != (z[1], z[2], nowa_data):
            pelne.append((z[0], z[1], z[2], nowa_data))
    if not pelne:
        return {"zmienione": 0}
    db.execute("DELETE FROM plan_zmiany WHERE op IN (SELECT op FROM plan_ops WHERE cofnieta=1)")
    db.execute("DELETE FROM plan_ops WHERE cofnieta=1")
    op = db.execute("INSERT INTO plan_ops(opis, czas) VALUES (?,?)", (opis, time.time())).lastrowid
    db.executemany("INSERT INTO plan_zmiany(op, id, stary_cel, stary_pom, nowy_cel, nowy_pom, stara_data, nowa_data) "
                   "VALUES (?,?,?,?,?,?,?,?)",
                   [(op, i, stare[i]["cel"], stare[i]["pominiety"], c, p, stare[i]["data"], d) for i, c, p, d in pelne])
    db.executemany("UPDATE plan SET cel=?, pominiety=?, data=? WHERE id=?", [(c, p, d, i) for i, c, p, d in pelne])
    db.commit()
    return {"zmienione": len(pelne), "op": op}


def _wolne_w_folderze(db, folder: str, nazwy: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Dopisuje „ (2)”, gdy w folderze docelowym jest już plik o tej nazwie."""
    zajete = {_klucz(r[0]) for r in db.execute(
        "SELECT cel FROM plan WHERE pominiety=0 AND cel LIKE ? ESCAPE '\\'", (_like(folder + "/") + "%",))}
    ids = {i for i, _ in nazwy}
    zajete -= {_klucz(r[0]) for r in db.execute(
        f"SELECT cel FROM plan WHERE id IN ({','.join('?' * len(ids))})", list(ids))} if ids else set()
    wynik = []
    for i, n in nazwy:
        c = _wolna_nazwa(f"{folder}/{n}" if folder else n, zajete)
        zajete.add(_klucz(c))
        wynik.append((i, c))
    return wynik


def zmien_nazwe_folderu(db: sqlite3.Connection, stara: str, nowa: str) -> dict:
    przygotuj(db)
    stara, nowa = stara.strip("/"), czysta_sciezka(nowa)
    if not stara or not nowa:
        return {"blad": "Podaj nazwę folderu."}
    if _klucz(nowa).startswith(_klucz(stara) + "/"):
        return {"blad": "Nie można przenieść folderu do jego własnego podfolderu."}
    wiersze = db.execute("SELECT id, cel, pominiety FROM plan WHERE tryb!='istniejacy' AND cel LIKE ? ESCAPE '\\'",
                         (_like(stara + "/") + "%",)).fetchall()
    if not wiersze:
        return {"blad": "W tym folderze nie ma plików, które można przenieść."}
    grupy = defaultdict(list)
    for r in wiersze:
        rel = r["cel"][len(stara) + 1:]
        podf, nazwa = rel.rsplit("/", 1) if "/" in rel else ("", rel)
        grupy[nowa + ("/" + podf if podf else "")].append((r["id"], nazwa, r["pominiety"]))
    zmiany = []
    for folder, pl in grupy.items():
        for (i, c), (_, _, pom) in zip(_wolne_w_folderze(db, folder, [(i, n) for i, n, _ in pl]), pl):
            zmiany.append((i, c, pom))
    scal = db.execute("SELECT 1 FROM plan WHERE cel LIKE ? ESCAPE '\\' AND id NOT IN (%s) LIMIT 1"
                      % ",".join(str(r["id"]) for r in wiersze), (_like(nowa + "/") + "%",)).fetchone() is not None
    w = _zastosuj(db, f"Zmiana nazwy: {stara} → {nowa}", zmiany)
    w["scalono"] = scal
    return w


def przenies_pliki(db: sqlite3.Connection, ids: list[int], folder: str, opis: str | None = None) -> dict:
    przygotuj(db)
    folder = czysta_sciezka(folder)
    if not ids:
        return {"zmienione": 0}
    wiersze = db.execute(f"SELECT id, cel, pominiety FROM plan WHERE tryb!='istniejacy' AND id IN "
                         f"({','.join('?' * len(ids))})", [int(i) for i in ids]).fetchall()
    nazwy = [(r["id"], r["cel"].rsplit("/", 1)[-1]) for r in wiersze]
    pom = {r["id"]: r["pominiety"] for r in wiersze}
    return _zastosuj(db, opis or f"Przeniesienie {len(nazwy)} plików do {folder or '(główny folder)'}",
                     [(i, c, pom[i]) for i, c in _wolne_w_folderze(db, folder, nazwy)])


def wyklucz(db: sqlite3.Connection, ids: list[int] | None = None, folder: str | None = None,
            wartosc: bool = True) -> dict:
    przygotuj(db)
    if folder is not None:
        wiersze = db.execute("SELECT id, cel FROM plan WHERE tryb!='istniejacy' AND stan='nowy' AND "
                             "(cel LIKE ? ESCAPE '\\')", (_like(folder.strip("/") + "/") + "%",)).fetchall()
    else:
        wiersze = db.execute(f"SELECT id, cel FROM plan WHERE tryb!='istniejacy' AND id IN "
                             f"({','.join('?' * len(ids or []))})", [int(i) for i in ids or []]).fetchall()
    opis = ("Wykluczenie" if wartosc else "Przywrócenie") + (f" folderu {folder}" if folder else f" {len(wiersze)} plików")
    return _zastosuj(db, opis, [(r["id"], r["cel"], 1 if wartosc else 0) for r in wiersze])


def cofnij(db: sqlite3.Connection) -> dict:
    przygotuj(db)
    op = _ostatnia_op(db, 0)
    if not op:
        return {"zmienione": 0}
    zm = db.execute("SELECT id, stary_cel, stary_pom, stara_data, nowa_data FROM plan_zmiany WHERE op=?",
                    (op["op"],)).fetchall()
    db.executemany("UPDATE plan SET cel=?, pominiety=?, data=COALESCE(?, data) WHERE id=?",
                   [(r[1], r[2], r[3] if r[4] is not None else None, r[0]) for r in zm])
    db.execute("UPDATE plan_ops SET cofnieta=1 WHERE op=?", (op["op"],))
    db.commit()
    return {"zmienione": len(zm), "opis": op["opis"]}


def ponow(db: sqlite3.Connection) -> dict:
    przygotuj(db)
    op = _ostatnia_op(db, 1)
    if not op:
        return {"zmienione": 0}
    zm = db.execute("SELECT id, nowy_cel, nowy_pom, nowa_data FROM plan_zmiany WHERE op=?", (op["op"],)).fetchall()
    db.executemany("UPDATE plan SET cel=?, pominiety=?, data=COALESCE(?, data) WHERE id=?",
                   [(r[1], r[2], r[3], r[0]) for r in zm])
    db.execute("UPDATE plan_ops SET cofnieta=0 WHERE op=?", (op["op"],))
    db.commit()
    return {"zmienione": len(zm), "opis": op["opis"]}


def zastosuj_kategorie(db: sqlite3.Connection) -> dict:
    """Po decyzjach (dokumenty, „nie z aparatu”): przekłada pliki w istniejącym planie.
    Dokument -> Dokumenty/Dokumenty z RRRR, śmieci -> Odłożone/Śmieci, zdjęcie -> tam, gdzie zwykłe zdjęcie."""
    if not istnieje(db):
        return {"zmienione": 0}
    przygotuj(db)
    dok = analiza.dokumenty_potwierdzone(db)
    dec = kategorie.decyzje(db)
    zmiany_kat: dict[int, str | None] = {}
    grupy: dict[str, list] = defaultdict(list)
    for w in db.execute("SELECT id, sciezka, cel, alt, kat, data, pominiety FROM plan WHERE tryb!='istniejacy'"):
        d_uz = dec.get(w["sciezka"])
        folder = w["cel"].rsplit("/", 1)[0]
        w_kategorii = folder.startswith(DOKUMENTY + "/") or folder.startswith(kategorie.SMIECI)
        if d_uz == "smieci":
            cel_f, k = (folder if folder.startswith(kategorie.SMIECI) else folder_smieci(w)), "smieci"
        elif d_uz == "dokument" or (w["sciezka"] in dok and d_uz != "zdjecie"):
            cel_f, k = folder_dokumentow(w["data"]), "dokument"
        elif d_uz == "zdjecie" or (w["kat"] == "dokument" and w["sciezka"] not in dok):
            cel_f, k = (w["alt"].rsplit("/", 1)[0] if w["alt"] and w_kategorii else folder), None
        else:
            continue
        if k != w["kat"]:
            zmiany_kat[w["id"]] = k
        if cel_f != folder:
            grupy[cel_f].append(w)
    zmiany = []
    for f, lista in grupy.items():
        for (i, c), w in zip(_wolne_w_folderze(db, f, [(w["id"], w["cel"].rsplit("/", 1)[-1]) for w in lista]), lista):
            zmiany.append((i, c, w["pominiety"]))
    for i, k in zmiany_kat.items():
        uw = db.execute("SELECT uwaga FROM plan WHERE id=?", (i,)).fetchone()[0] or ""
        uw = _UWAGA_PODEJRZANE.sub("", uw).strip("; ") or None  # decyzja podjęta — pytanie znika
        db.execute("UPDATE plan SET kat=?, uwaga=? WHERE id=?", (k, uw, i))
    if not zmiany:
        db.commit()
        return {"zmienione": 0}
    return _zastosuj(db, f"Kategorie (dokumenty / śmieci / zdjęcia): {len(zmiany)} plików", zmiany)


# --- wyszukiwanie i zmiany zbiorcze --------------------------------------------------

FILTRY = {
    "": "1",
    "uwagi": "uwaga IS NOT NULL AND tryb!='istniejacy' AND pominiety=0",
    "bez_gps": "uwaga LIKE '%bez GPS%' AND pominiety=0",
    "data_z_pliku": "uwaga LIKE '%data z pliku%' AND pominiety=0",
    "pominiete": "pominiety=1 AND tryb!='istniejacy'",
    "smieci": "kat='smieci' AND tryb!='istniejacy'",
    "nie_z_aparatu": "kat='podejrzane' AND tryb!='istniejacy'",
    "dokumenty": "kat='dokument' AND tryb!='istniejacy'",
    "bledy": "wynik LIKE 'blad%'",
    "kolizje": "pominiety=0 AND lower(cel) IN (SELECT lower(cel) FROM plan WHERE pominiety=0 GROUP BY lower(cel) "
               "HAVING COUNT(*) > 1)",
}


def szukaj(db: sqlite3.Connection, tekst: str = "", filtr: str = "", od: int = 0, ile: int = 200) -> dict:
    przygotuj(db)
    warunek = FILTRY.get(filtr, "1")
    tekst = (tekst or "").strip().casefold()
    wiersze = [dict(r) for r in db.execute(
        f"""SELECT id, plik_id, sciezka, rodzaj, rozmiar, data, cel, tryb, stan, pominiety, uwaga, wynik
            FROM plan WHERE {warunek} ORDER BY cel""")]
    if tekst:
        wiersze = [w for w in wiersze if tekst in w["cel"].casefold() or tekst in w["sciezka"].casefold()]
    for w in wiersze:
        w["nazwa"] = w["cel"].rsplit("/", 1)[-1]
    return {"folder": None, "razem": len(wiersze), "pliki": wiersze[od:od + ile]}


def _data_pliku(w) -> datetime | None:
    d = _dt(w["data"])
    if d:
        return d
    m = re.search(r"(?:Zdjęcia|Filmy) z (\d{4})/(\S+)", w["cel"])
    if m and m.group(2) in MIESIACE:
        return datetime(int(m.group(1)), MIESIACE.index(m.group(2)) + 1, 1)
    return None


def _fraza_folderu(cel: str) -> str:
    """„Marzec w Olkuszu” -> „w Olkuszu” (fraza miejsca z nazwy folderu miesiąca)."""
    folder = cel.rsplit("/", 1)[0].rsplit("/", 1)[-1] if "/" in cel else ""
    slowa = folder.split(" ", 1)
    return slowa[1] if len(slowa) > 1 and slowa[0] in MIESIACE else ""


def _folder_mediow(w, d: datetime, fraza: str) -> str:
    rodz = "Zdjęcia" if w["rodzaj"] == "zdjecie" else "Filmy"
    return f"{rodz}/{rodz} z {d.year}/" + czysta_nazwa(f"{MIESIACE[d.month - 1]} {fraza}".strip())


def ustaw_miejsce(db: sqlite3.Connection, ids: list[int], miejsce: str) -> dict:
    """„Te zdjęcia to też Hel” — przenosi do <Miesiąc> na Helu (miesiąc z daty każdego pliku)."""
    przygotuj(db)
    m = (miejsce or "").strip()
    if not m:
        return {"blad": "Podaj nazwę miejsca, np. Hel albo dom."}
    if m.casefold() in ("dom", "w domu"):
        fraza = "w domu"
    elif re.match(r"^(w|we|na)\s", m):
        fraza = m  # użytkownik podał już odmienioną formę
    else:
        fraza = miejsca.miejscownik(m[0].upper() + m[1:])[0]
    return _przeloz_media(db, ids, lambda w, d: (d, fraza), f"Miejsce „{fraza}” dla")


def ustaw_date(db: sqlite3.Connection, ids: list[int], data: str) -> dict:
    """Poprawia datę (np. skany ze złą datą) i przenosi do właściwego roku/miesiąca, zachowując miejsce."""
    przygotuj(db)
    mm = re.fullmatch(r"\s*(\d{4})-(\d{1,2})(?:-(\d{1,2}))?\s*", data or "")
    if not mm:
        return {"blad": "Podaj datę w formacie RRRR-MM-DD albo RRRR-MM."}
    try:
        d = datetime(int(mm.group(1)), int(mm.group(2)), int(mm.group(3) or 1), 12)
    except ValueError:
        return {"blad": "Nieprawidłowa data."}
    return _przeloz_media(db, ids, lambda w, _d: (d, _fraza_folderu(w["cel"])), f"Data {d:%Y-%m-%d} dla",
                          nowa_data=d.isoformat(timespec="seconds"))


def _przeloz_media(db, ids, wybor, opis: str, nowa_data: str | None = None) -> dict:
    wiersze = db.execute(f"SELECT id, cel, rodzaj, data, pominiety FROM plan WHERE tryb!='istniejacy' AND id IN "
                         f"({','.join('?' * len(ids))})", [int(i) for i in ids]).fetchall() if ids else []
    grupy, pominiete = defaultdict(list), 0
    for w in wiersze:
        d = _data_pliku(w)
        if w["rodzaj"] not in ("zdjecie", "film") or (d is None and nowa_data is None):
            pominiete += 1
            continue
        dd, fraza = wybor(w, d)
        grupy[_folder_mediow(w, dd, fraza)].append(w)
    zmiany = []
    for folder, lista in grupy.items():
        for (i, c), w in zip(_wolne_w_folderze(db, folder, [(w["id"], w["cel"].rsplit("/", 1)[-1]) for w in lista]),
                             lista):
            zmiany.append((i, c, w["pominiety"], nowa_data or w["data"]))
    wynik = _zastosuj(db, f"{opis} {len(zmiany)} plików", zmiany)
    wynik["pominiete"] = pominiete
    wynik["foldery"] = sorted(grupy)
    return wynik
