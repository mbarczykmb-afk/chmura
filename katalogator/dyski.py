"""Przeglądanie dysków i folderów (drzewo „jak w commanderze”)."""

from __future__ import annotations

import os
import re
import shutil
import string
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as Timeout

from . import typy

WINDOWS = sys.platform == "win32"
_UKRYTY_SYSTEMOWY = 0x2 | 0x4  # FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM
_ZLE_ZNAKI = re.compile(r'[\\/:*?"<>|]')
_pula = ThreadPoolExecutor(max_workers=8)


def _klucz(sciezka: str) -> str:
    s = os.path.normpath(sciezka)
    return s.lower() if WINDOWS else s


def zawiera(rodzic: str, dziecko: str) -> bool:
    """Czy `dziecko` leży wewnątrz `rodzic` (albo jest tym samym folderem)."""
    r, d = _klucz(rodzic), _klucz(dziecko)
    if r == d:
        return True
    prefiks = r if r.endswith(os.sep) else r + os.sep
    return d.startswith(prefiks)


def normalizuj_wybor(sciezki: list[str]) -> list[str]:
    """Usuwa duplikaty i foldery zawarte w innych wybranych (rodzic obejmuje dzieci)."""
    wynik: list[str] = []
    for s in sorted({os.path.normpath(s.strip()) for s in sciezki if s and s.strip()}, key=len):
        if not any(zawiera(w, s) for w in wynik):
            wynik.append(s)
    return wynik


# --- dyski ------------------------------------------------------------------

def _info_windows(litera: str) -> dict:
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.windll.kernel32
    korzen = f"{litera}:\\"
    typ = k32.GetDriveTypeW(korzen)
    rodzaj = {2: "wymienny", 3: "lokalny", 4: "sieciowy", 5: "CD/DVD", 6: "RAM"}.get(typ, "inny")
    d = {"sciezka": korzen, "litera": litera, "rodzaj": rodzaj, "etykieta": "", "siec": "",
         "wolne": None, "razem": None, "dostepny": True}
    if typ == 4:
        bufor = ctypes.create_unicode_buffer(1024)
        dl = wintypes.DWORD(1024)
        if ctypes.windll.mpr.WNetGetConnectionW(f"{litera}:", bufor, ctypes.byref(dl)) == 0:
            d["siec"] = bufor.value
    etykieta = ctypes.create_unicode_buffer(261)
    if k32.GetVolumeInformationW(korzen, etykieta, 261, None, None, None, None, 0):
        d["etykieta"] = etykieta.value
    try:
        u = shutil.disk_usage(korzen)
        d["wolne"], d["razem"] = u.free, u.total
    except OSError:
        d["dostepny"] = False
    return d


def lista_dyskow() -> list[dict]:
    if not WINDOWS:
        wynik = [{"sciezka": "/", "litera": "", "rodzaj": "lokalny", "etykieta": "System",
                  "siec": "", "wolne": None, "razem": None, "dostepny": True}]
        for s in (os.path.expanduser("~"), "/mnt", "/media"):
            if os.path.isdir(s) and s != "/":
                wynik.append({"sciezka": s, "litera": "", "rodzaj": "lokalny", "etykieta": os.path.basename(s),
                              "siec": "", "wolne": None, "razem": None, "dostepny": True})
        return wynik

    import ctypes
    maska = ctypes.windll.kernel32.GetLogicalDrives()
    litery = [lit for i, lit in enumerate(string.ascii_uppercase) if maska >> i & 1]
    # Odłączony dysk sieciowy potrafi „wisieć” — każdy sprawdzamy z limitem czasu.
    zadania = {lit: _pula.submit(_info_windows, lit) for lit in litery}
    wynik = []
    for lit, z in zadania.items():
        try:
            d = z.result(timeout=3)
        except Timeout:
            d = {"sciezka": f"{lit}:\\", "litera": lit, "rodzaj": "sieciowy", "etykieta": "",
                 "siec": "", "wolne": None, "razem": None, "dostepny": False}
        except Exception:
            continue
        if d["rodzaj"] == "CD/DVD" and not d["dostepny"]:
            continue
        wynik.append(d)
    return wynik


# --- foldery ----------------------------------------------------------------

def _ukryty(w: os.DirEntry) -> bool:
    if typy.pominac_folder(w.name) or w.name.startswith("$"):
        return True
    if WINDOWS:
        try:
            return bool(getattr(w.stat(follow_symlinks=False), "st_file_attributes", 0) & _UKRYTY_SYSTEMOWY)
        except OSError:
            return True
    return False


def _podfoldery(sciezka: str) -> list[dict]:
    wynik = []
    with os.scandir(sciezka) as it:
        for w in it:
            try:
                if w.is_dir(follow_symlinks=False) and not _ukryty(w):
                    wynik.append({"nazwa": w.name, "sciezka": os.path.join(sciezka, w.name)})
            except OSError:
                continue
    wynik.sort(key=lambda x: x["nazwa"].lower())
    return wynik


def podfoldery(sciezka: str, limit_czasu: float = 15) -> dict:
    sciezka = os.path.normpath(sciezka)
    if WINDOWS and re.fullmatch(r"[A-Za-z]:", sciezka):
        sciezka += "\\"
    try:
        return {"sciezka": sciezka, "foldery": _pula.submit(_podfoldery, sciezka).result(timeout=limit_czasu)}
    except Timeout:
        return {"sciezka": sciezka, "foldery": [], "blad": "Dysk nie odpowiada."}
    except PermissionError:
        return {"sciezka": sciezka, "foldery": [], "blad": "Brak dostępu."}
    except OSError as e:
        return {"sciezka": sciezka, "foldery": [], "blad": e.strerror or str(e)}


def nowy_folder(w: str, nazwa: str) -> dict:
    nazwa = (nazwa or "").strip()
    if not nazwa or _ZLE_ZNAKI.search(nazwa) or nazwa in (".", ".."):
        return {"blad": 'Niedozwolona nazwa (bez znaków \\ / : * ? " < > |).'}
    cel = os.path.join(os.path.normpath(w), nazwa)
    try:
        os.makedirs(cel, exist_ok=False)
    except FileExistsError:
        return {"blad": "Taki folder już istnieje.", "sciezka": cel}
    except OSError as e:
        return {"blad": e.strerror or str(e)}
    return {"sciezka": cel}
