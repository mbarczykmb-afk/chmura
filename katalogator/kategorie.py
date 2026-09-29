"""Kategorie plików poza zwykłymi zdjęciami: śmieci (ikony, pliki tymczasowe…) i obrazy „nie z aparatu”.

- śmieci trafiają automatycznie do `Odłożone/Śmieci` (widać je w drzewie, można przywrócić),
- obrazy, które chyba nie są zdjęciami z aparatu (grafiki PNG/GIF, zrzuty ekranu, pobrane z internetu,
  małe obrazki bez danych aparatu), czekają na decyzję: zdjęcie / dokument / śmieci.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import PurePath

SCHEMAT = """
CREATE TABLE IF NOT EXISTS kategorie (
    sciezka   TEXT PRIMARY KEY,
    kategoria TEXT NOT NULL          -- 'zdjecie' | 'dokument' | 'smieci' (decyzja użytkownika)
);
"""
ODLOZONE = "Odłożone"
SMIECI = ODLOZONE + "/Śmieci"
KATEGORIE = ("zdjecie", "dokument", "smieci")

_EXT_SMIECI = {".ico", ".cur", ".icns", ".ani", ".tmp", ".temp", ".crdownload", ".part", ".partial",
               ".download", ".lnk", ".url", ".thumb", ".thumbdata"}
_GRAFIKI = {".png", ".gif", ".webp", ".bmp"}
_RAW = {".dng", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2", ".raf", ".tif", ".tiff", ".heic", ".heif"}
_SCIEZKA_SMIECI = re.compile(r"(^|[\\/])(\.?thumbnails?|thumbs|cache|\.cache|temp|tmp|"
                             r"whatsapp stickers|stickers)([\\/]|$)", re.I)
_NAZWA_SMIECI = re.compile(r"(^|[_.\-])(thumb|thumbnail|icon|favicon|sprite)([_.\-]|\d|$)", re.I)
_ZRZUT = re.compile(r"screenshot|zrzut|screen_shot|scr_|capture", re.I)
_POBRANE = re.compile(r"(^|[\\/])(download|downloads|pobrane|internet|facebook|messenger|instagram|"
                      r"memy|memes|tapety|wallpapers?|gify|gifs)([\\/]|$)", re.I)
_Z_TELEFONU = re.compile(r"^(img|pxl|dsc|dscn|dscf|p\d{7}|vid|mvimg|photo|wp_|signal-|img-\d{8}-wa)", re.I)
MALY_BOK = 256     # ikona / miniatura
SREDNI_BOK = 1000  # mniejsze obrazy bez danych aparatu są podejrzane


def _wzgledna(p: dict) -> str:
    """Ścieżka wewnątrz skanowanego folderu — nazwy folderów nad nim (np. …\\Temp) nie mają znaczenia."""
    return p.get("wzgledna") or os.path.basename(p["sciezka"])


def przygotuj(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMAT)


def smieci(p: dict, wymiary: tuple | None = None) -> str | None:
    """Powód, dla którego plik to śmieć — albo None."""
    nazwa = os.path.basename(p["sciezka"])
    ext = PurePath(nazwa).suffix.lower()
    if p["rozmiar"] == 0:
        return "pusty plik"
    if ext in _EXT_SMIECI:
        return "ikona / plik tymczasowy / skrót"
    if _SCIEZKA_SMIECI.search(os.path.dirname(_wzgledna(p))):
        return "miniatury / pamięć podręczna"
    if p["rodzaj"] == "zdjecie" and not (p.get("aparat") or p.get("lat") is not None or p.get("zrodlo_daty") == "exif"):
        # zdjęcie z danymi aparatu / GPS / datą EXIF nigdy nie jest „ikoną”
        if wymiary and wymiary[0] and max(wymiary) <= MALY_BOK:
            return f"mały obrazek {wymiary[0]}×{wymiary[1]} (ikona / miniatura)"
        if _NAZWA_SMIECI.search(PurePath(nazwa).stem):
            return "miniatura / ikona (nazwa pliku)"
    return None


def podejrzane(p: dict, wymiary: tuple | None = None) -> str | None:
    """Powód, dla którego obraz chyba nie jest zdjęciem z aparatu — albo None."""
    if p["rodzaj"] != "zdjecie" or p.get("aparat"):
        return None
    nazwa = os.path.basename(p["sciezka"])
    ext = PurePath(nazwa).suffix.lower()
    if ext in _RAW:
        return None
    if _ZRZUT.search(nazwa):
        return "zrzut ekranu"
    if ext in _GRAFIKI:
        return f"grafika {ext[1:].upper()} bez danych aparatu"
    if _POBRANE.search(os.path.dirname(_wzgledna(p))):
        return "z folderu pobranych / internetu"
    if wymiary and wymiary[0] and max(wymiary) < SREDNI_BOK:
        return f"mały obraz {wymiary[0]}×{wymiary[1]} bez danych aparatu"
    if p.get("zrodlo_daty") == "plik" and not _Z_TELEFONU.match(nazwa):
        return "brak danych aparatu i daty zdjęcia"
    return None


def wymiary(db: sqlite3.Connection) -> dict[str, tuple]:
    try:
        return {r[0]: (r[1], r[2]) for r in db.execute(
            "SELECT a.sciezka, a.szer, a.wys FROM analiza a JOIN pliki p ON p.sciezka=a.sciezka "
            "AND p.rozmiar=a.rozmiar AND p.mtime=a.mtime WHERE a.szer IS NOT NULL")}
    except sqlite3.OperationalError:
        return {}


def decyzje(db: sqlite3.Connection) -> dict[str, str]:
    przygotuj(db)
    return {r[0]: r[1] for r in db.execute("SELECT sciezka, kategoria FROM kategorie")}


def do_sprawdzenia(db: sqlite3.Connection) -> list[dict]:
    """Obrazy „nie z aparatu” (najpierw bez decyzji) z powodem i ewentualną decyzją."""
    przygotuj(db)
    wym = wymiary(db)
    dec = decyzje(db)
    dok = {r[0]: r[1] for r in db.execute("SELECT sciezka, dokument FROM decyzje_dok")} \
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='decyzje_dok'").fetchone() else {}
    wynik = []
    for r in db.execute("SELECT rowid id, sciezka, wzgledna, rozmiar, rodzaj, aparat, data, zrodlo_daty "
                        "FROM pliki WHERE rodzaj='zdjecie' AND aparat IS NULL ORDER BY sciezka"):
        p = dict(r)
        w = wym.get(p["sciezka"])
        if smieci(p, w):
            continue  # oczywiste śmieci nie wymagają pytania (są w Odłożone/Śmieci)
        powod = podejrzane(p, w)
        if not powod:
            continue
        p["powod"] = powod
        p["szer"], p["wys"] = w if w else (None, None)
        p["decyzja"] = dec.get(p["sciezka"]) or ("dokument" if dok.get(p["sciezka"]) == 1 else None)
        wynik.append(p)
    wynik.sort(key=lambda p: p["decyzja"] is not None)
    return wynik


def zapisz(db: sqlite3.Connection, wybor: dict) -> dict:
    """wybor: {id pliku: 'zdjecie'|'dokument'|'smieci'}. Dokument = też potwierdzenie w decyzjach dokumentów."""
    przygotuj(db)
    n = 0
    for i, kat in wybor.items():
        if kat not in KATEGORIE:
            continue
        r = db.execute("SELECT sciezka FROM pliki WHERE rowid=?", (int(i),)).fetchone()
        if not r:
            continue
        db.execute("INSERT OR REPLACE INTO kategorie VALUES (?,?)", (r[0], kat))
        db.execute("INSERT OR REPLACE INTO decyzje_dok VALUES (?,?)", (r[0], 1 if kat == "dokument" else 0))
        n += 1
    db.commit()
    return {"zapisane": n}
