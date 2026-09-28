"""Analiza zdjęć: wykrywanie zdjęć dokumentów, podobnych zdjęć i nieostrych.

Żeby nie czytać całych plików przez sieć, korzystamy z miniatury zapisanej przez aparat
w nagłówku EXIF (pierwsze ~256 KB pliku). Pełny obraz dekodujemy tylko, gdy jej brak.
Wyniki trafiają do tabeli `analiza` i są liczone ponownie tylko dla zmienionych plików.
"""

from __future__ import annotations

import io
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageFilter, ImageOps, ImageStat

from .skaner import Przerwano

SCHEMAT = """
CREATE TABLE IF NOT EXISTS analiza (
    sciezka  TEXT PRIMARY KEY,
    rozmiar  INTEGER NOT NULL,
    mtime    REAL NOT NULL,
    dhash    TEXT,
    dokument REAL,
    ostrosc  REAL,
    szer     INTEGER,
    wys      INTEGER,
    blad     TEXT
);
CREATE TABLE IF NOT EXISTS decyzje_dok (
    sciezka  TEXT PRIMARY KEY,
    dokument INTEGER NOT NULL
);
"""
NAGLOWEK = 256 * 1024
PROG_KANDYDAT = 0.55   # od tej oceny zdjęcie pokazujemy jako możliwy dokument
PROG_PEWNY = 0.72      # od tej — wstępnie zaznaczone
PROG_PODOBNE = 5       # maks. różnica bitów odcisku obrazu
_ZRZUT = re.compile(r"screenshot|zrzut|screen_shot|scr_", re.IGNORECASE)
_ORIENTACJA = {2: (Image.Transpose.FLIP_LEFT_RIGHT,), 3: (Image.Transpose.ROTATE_180,),
               4: (Image.Transpose.FLIP_TOP_BOTTOM,), 5: (Image.Transpose.TRANSPOSE,),
               6: (Image.Transpose.ROTATE_270,), 7: (Image.Transpose.TRANSVERSE,),
               8: (Image.Transpose.ROTATE_90,)}


def przygotuj(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMAT)


def miniatura(sciezka: str, min_bok: int = 100) -> tuple[Image.Image, tuple[int, int] | None]:
    """(mały obraz RGB we właściwej orientacji, rozmiar oryginału)."""
    with open(sciezka, "rb") as f:
        glowa = f.read(NAGLOWEK)
    rozmiar, orientacja, mini = None, 1, None
    try:
        with Image.open(io.BytesIO(glowa)) as im:
            rozmiar = im.size
            orientacja = im.getexif().get(0x0112, 1) or 1
    except Exception:
        pass
    if glowa[:2] == b"\xff\xd8":
        i = glowa.find(b"\xff\xd8\xff", 2)
        j = glowa.find(b"\xff\xd9", i + 2) if i > 0 else -1
        if i > 0 and j > 0:
            try:
                kandydat = Image.open(io.BytesIO(glowa[i:j + 2]))
                kandydat.load()
                if min(kandydat.size) >= min_bok * 0.75:
                    mini = kandydat.convert("RGB")
                    for t in _ORIENTACJA.get(orientacja, ()):
                        mini = mini.transpose(t)
            except Exception:
                mini = None
    if mini is None:
        with Image.open(sciezka) as im:
            rozmiar = rozmiar or im.size
            im.draft("RGB", (min_bok * 3, min_bok * 3))
            mini = ImageOps.exif_transpose(im).convert("RGB")
            mini.thumbnail((min_bok * 3, min_bok * 3))
    return mini, rozmiar


def dhash(im: Image.Image) -> int:
    g = im.convert("L").resize((9, 8), Image.Resampling.BILINEAR)
    px = g.tobytes()
    bity = 0
    for y in range(8):
        for x in range(8):
            bity = (bity << 1) | (px[y * 9 + x] > px[y * 9 + x + 1])
    return bity


def ostrosc(im: Image.Image) -> float:
    g = im.convert("L")
    g.thumbnail((256, 256))
    return float(ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).var[0])


def ocena_dokumentu(im: Image.Image) -> float:
    """0..1 — jak bardzo obraz przypomina zdjęcie kartki/paragonu/dokumentu."""
    im = im.copy()
    im.thumbnail((160, 160))
    g = im.convert("L")
    hist = g.histogram()
    n = sum(hist) or 1
    jasne = sum(hist[170:]) / n
    ciemne = sum(hist[:90]) / n
    nasycenie = ImageStat.Stat(im.convert("HSV")).mean[1] / 255
    krawedzie = g.filter(ImageFilter.FIND_EDGES)
    ostre = sum(krawedzie.histogram()[60:]) / n

    def ogr(x):
        return max(0.0, min(1.0, x))

    s_papier = ogr((jasne - 0.30) / 0.40)
    s_kolor = 1 - ogr((nasycenie - 0.10) / 0.25)
    s_tusz = 1.0 if 0.01 <= ciemne <= 0.35 else (ogr(ciemne / 0.01) if ciemne < 0.01 else ogr(1 - (ciemne - 0.35) / 0.3))
    s_tekst = ogr((ostre - 0.03) / 0.12)
    return round(0.35 * s_papier + 0.25 * s_kolor + 0.15 * s_tusz + 0.25 * s_tekst, 3)


def _analizuj_plik(w) -> tuple:
    try:
        im, rozm = miniatura(w["sciezka"])
        h = dhash(im)
        return (w["sciezka"], w["rozmiar"], w["mtime"], f"{h:016x}", ocena_dokumentu(im), ostrosc(im),
                rozm[0] if rozm else im.width, rozm[1] if rozm else im.height, None)
    except Exception as e:
        return (w["sciezka"], w["rozmiar"], w["mtime"], None, None, None, None, None, f"{type(e).__name__}: {e}"[:200])


def analizuj(db: sqlite3.Connection, postep=None, przerwij=None, watki: int = 4) -> dict:
    przygotuj(db)
    wiersze = db.execute(
        """SELECT p.sciezka, p.rozmiar, p.mtime FROM pliki p
           LEFT JOIN analiza a ON a.sciezka = p.sciezka AND a.rozmiar = p.rozmiar AND a.mtime = p.mtime
           WHERE p.rodzaj = 'zdjecie' AND a.sciezka IS NULL"""
    ).fetchall()
    if postep:
        postep("analiza zdjęć", 0, len(wiersze), 0)

    def zadanie(w):
        if przerwij is not None and przerwij.is_set():
            raise Przerwano(w["sciezka"])
        return _analizuj_plik(w)

    with ThreadPoolExecutor(max_workers=watki) as pula:
        for i, wynik in enumerate(pula.map(zadanie, wiersze), 1):
            db.execute("INSERT OR REPLACE INTO analiza VALUES (?,?,?,?,?,?,?,?,?)", wynik)
            if i % 50 == 0:
                db.commit()
                if postep:
                    postep("analiza zdjęć", i, len(wiersze), 0)
    db.commit()
    if postep:
        postep("analiza zdjęć", len(wiersze), len(wiersze), 0)
    return podsumowanie(db)


_AKTUALNE = "a.sciezka = p.sciezka AND a.rozmiar = p.rozmiar AND a.mtime = p.mtime"


def podsumowanie(db: sqlite3.Connection) -> dict:
    przygotuj(db)
    r = db.execute(f"SELECT COUNT(*) n FROM pliki p JOIN analiza a ON {_AKTUALNE} WHERE p.rodzaj='zdjecie'").fetchone()
    wsz = db.execute("SELECT COUNT(*) n FROM pliki WHERE rodzaj='zdjecie'").fetchone()
    return {"przeanalizowane": r["n"], "zdjecia": wsz["n"],
            "dokumenty": len(kandydaci_dokumentow(db, tylko_nowe=True)),
            "dokumenty_potwierdzone": db.execute("SELECT COUNT(*) FROM decyzje_dok WHERE dokument=1").fetchone()[0],
            "podobne_grupy": len(grupy_podobnych(db))}


# --- dokumenty ---------------------------------------------------------------------

def kandydaci_dokumentow(db: sqlite3.Connection, tylko_nowe: bool = False) -> list[dict]:
    przygotuj(db)
    wiersze = db.execute(
        f"""SELECT p.rowid id, p.sciezka, p.wzgledna, p.data, a.dokument ocena, d.dokument decyzja
            FROM pliki p JOIN analiza a ON {_AKTUALNE}
            LEFT JOIN decyzje_dok d ON d.sciezka = p.sciezka
            WHERE p.rodzaj='zdjecie' AND (a.dokument >= ? OR d.dokument = 1)
            ORDER BY a.dokument DESC""", (PROG_KANDYDAT,)).fetchall()
    wynik = []
    for w in wiersze:
        if _ZRZUT.search(w["wzgledna"]):
            continue  # zrzuty ekranu zostają ze zdjęciami
        if tylko_nowe and w["decyzja"] is not None:
            continue
        d = dict(w)
        d["zaznacz"] = bool(w["decyzja"]) if w["decyzja"] is not None else w["ocena"] >= PROG_PEWNY
        wynik.append(d)
    return wynik


def zapisz_decyzje(db: sqlite3.Connection, tak: list[int], nie: list[int]) -> dict:
    przygotuj(db)
    for ids, wart in ((tak, 1), (nie, 0)):
        for i in ids:
            r = db.execute("SELECT sciezka FROM pliki WHERE rowid=?", (i,)).fetchone()
            if r:
                db.execute("INSERT OR REPLACE INTO decyzje_dok VALUES (?,?)", (r["sciezka"], wart))
    db.commit()
    return {"dokumenty": db.execute("SELECT COUNT(*) FROM decyzje_dok WHERE dokument=1").fetchone()[0]}


def dokumenty_potwierdzone(db: sqlite3.Connection) -> set[str]:
    przygotuj(db)
    return {r[0] for r in db.execute("SELECT sciezka FROM decyzje_dok WHERE dokument=1")}


# --- podobne i nieostre ----------------------------------------------------------------

def grupy_podobnych(db: sqlite3.Connection, prog: int = PROG_PODOBNE) -> list[list[dict]]:
    """Grupy wizualnie podobnych zdjęć (bez grup samych identycznych plików)."""
    przygotuj(db)
    wiersze = [dict(w) for w in db.execute(
        f"""SELECT p.rowid id, p.sciezka, p.korzen, p.wzgledna, p.mtime, p.rozmiar, p.data,
                   a.dhash, a.ostrosc, a.szer, a.wys, o.pelny
            FROM pliki p JOIN analiza a ON {_AKTUALNE}
            LEFT JOIN odciski o ON o.sciezka = p.sciezka AND o.rozmiar = p.rozmiar AND o.mtime = p.mtime
            WHERE p.rodzaj='zdjecie' AND a.dhash IS NOT NULL""")] if _ma_odciski(db) else [dict(w) for w in db.execute(
        f"""SELECT p.rowid id, p.sciezka, p.korzen, p.wzgledna, p.mtime, p.rozmiar, p.data,
                   a.dhash, a.ostrosc, a.szer, a.wys, NULL pelny
            FROM pliki p JOIN analiza a ON {_AKTUALNE}
            WHERE p.rodzaj='zdjecie' AND a.dhash IS NOT NULL""")]
    hashe = []
    for w in wiersze:
        h = int(w["dhash"], 16)
        if 6 <= h.bit_count() <= 58:  # pomijamy jednolite obrazy (czarne, białe)
            hashe.append((h, w))
    rodzic = list(range(len(hashe)))

    def znajdz(i):
        while rodzic[i] != i:
            rodzic[i] = rodzic[rodzic[i]]
            i = rodzic[i]
        return i

    # pasma: różnica <= prog bitów => co najmniej jedno z (prog+1) pasm identyczne
    pasma = prog + 1
    szer = 64 // pasma
    for b in range(pasma):
        przes = b * szer
        dl = szer if b < pasma - 1 else 64 - przes
        maska = (1 << dl) - 1
        kubelki: dict[int, list[int]] = {}
        for i, (h, _) in enumerate(hashe):
            kubelki.setdefault((h >> przes) & maska, []).append(i)
        for lista in kubelki.values():
            if len(lista) < 2 or len(lista) > 400:
                continue
            for x in range(len(lista)):
                for y in range(x + 1, len(lista)):
                    i, j = lista[x], lista[y]
                    if (hashe[i][0] ^ hashe[j][0]).bit_count() <= prog:
                        ri, rj = znajdz(i), znajdz(j)
                        if ri != rj:
                            rodzic[ri] = rj
    grupy: dict[int, list[dict]] = {}
    for i, (_, w) in enumerate(hashe):
        grupy.setdefault(znajdz(i), []).append(w)
    wynik = []
    for g in grupy.values():
        if len(g) < 2:
            continue
        pelne = {w["pelny"] for w in g}
        if len(pelne) == 1 and None not in pelne:
            continue  # same identyczne — to zakładka „Duplikaty”
        g.sort(key=lambda w: (-(w["szer"] or 0) * (w["wys"] or 0), -(w["ostrosc"] or 0), w["mtime"]))
        wynik.append(g)
    wynik.sort(key=lambda g: -len(g))
    return wynik


def _ma_odciski(db) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE name='odciski'").fetchone() is not None


def najmniej_ostre(db: sqlite3.Connection, ile: int = 120) -> list[dict]:
    przygotuj(db)
    return [dict(w) for w in db.execute(
        f"""SELECT p.rowid id, p.sciezka, p.wzgledna, p.data, a.ostrosc FROM pliki p JOIN analiza a ON {_AKTUALNE}
            WHERE p.rodzaj='zdjecie' AND a.ostrosc IS NOT NULL ORDER BY a.ostrosc LIMIT ?""", (ile,))]
