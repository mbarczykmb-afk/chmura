"""Analiza zdjęć: wykrywanie zdjęć dokumentów, podobnych zdjęć i nieostrych.

Żeby nie czytać całych plików przez sieć, korzystamy z miniatury zapisanej przez aparat
w nagłówku EXIF (pierwsze ~256 KB pliku). Pełny obraz dekodujemy tylko, gdy jej brak.
Wyniki trafiają do tabeli `analiza` i są liczone ponownie tylko dla zmienionych plików.
"""

from __future__ import annotations

import io
import operator
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat

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
PROG_WSTEPNY = 0.45    # etap 1 (miniatura): jasne, mało kolorowe — tylko te sprawdzamy dokładniej
PROG_KANDYDAT = 0.6    # etap 2 (tekst): od tej oceny zdjęcie pokazujemy jako możliwy dokument
PROG_PEWNY = 0.8       # od tej — wstępnie zaznaczone
PROG_PODOBNE = 8       # maks. różnica bitów odcisku obrazu (wstępne dopasowanie)
PROG_SZAROSCI = 14     # maks. średnia różnica jasności podpisów 8×8 (0–255)
PROG_KOLORU = 16       # maks. średnia różnica kolorów podpisów 4×4
_ZRZUT = re.compile(r"screenshot|zrzut|screen_shot|scr_", re.IGNORECASE)
_ORIENTACJA = {2: (Image.Transpose.FLIP_LEFT_RIGHT,), 3: (Image.Transpose.ROTATE_180,),
               4: (Image.Transpose.FLIP_TOP_BOTTOM,), 5: (Image.Transpose.TRANSPOSE,),
               6: (Image.Transpose.ROTATE_270,), 7: (Image.Transpose.TRANSVERSE,),
               8: (Image.Transpose.ROTATE_90,)}


def przygotuj(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMAT)
    kol = {r[1] for r in db.execute("PRAGMA table_info(analiza)")}
    for nazwa, typ in (("podpis", "TEXT"), ("tekst", "REAL")):  # kolumny od wersji 1.2.1
        if nazwa not in kol:
            db.execute(f"ALTER TABLE analiza ADD COLUMN {nazwa} {typ}")
    db.commit()


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


def podpis(im: Image.Image) -> str:
    """64 bajty jasności (8×8) + 48 bajtów koloru (4×4 RGB) — do potwierdzania podobieństwa."""
    return (im.convert("L").resize((8, 8), Image.Resampling.BOX).tobytes()
            + im.convert("RGB").resize((4, 4), Image.Resampling.BOX).tobytes()).hex()


def _roznice_podpisow(a: str, b: str) -> tuple[float, float]:
    return _roznice_bajtow(bytes.fromhex(a), bytes.fromhex(b))


def _roznice_bajtow(x: bytes, y: bytes) -> tuple[float, float]:
    szar = sum(map(abs, map(operator.sub, x[:64], y[:64]))) / 64
    kol = sum(map(abs, map(operator.sub, x[64:112], y[64:112]))) / 48
    return szar, kol


def _okresowosc(prof: list[float]) -> float:
    """Siła regularnego powtarzania się wierszy (tekst: wiersz, przerwa, wiersz…), 0–1."""
    n = len(prof)
    if n < 30:
        return 0.0
    sr = sum(prof) / n
    d = [v - sr for v in prof]
    war = sum(v * v for v in d)
    if war <= 1e-9:
        return 0.0
    ac = [sum(map(operator.mul, d, d[lag:])) / war for lag in range(min(90, n // 3))]  # map: kilka razy szybciej
    minimum = None
    for lag in range(2, len(ac)):
        if ac[lag] < 0 and (minimum is None or ac[lag] < ac[minimum]):
            minimum = lag
        elif minimum is not None and ac[lag] > ac[lag - 1] and ac[lag] > 0:
            break
    if minimum is None:  # brak naprzemienności — łagodne przejścia (niebo, sylwetka), nie tekst
        return 0.0
    return max(0.0, min(max(ac[minimum:]) - ac[minimum], 2.0) / 2)


def ocena_tekstu(im: Image.Image, bok: int = 1000, pasy: int = 10) -> float:
    """0..1 — czy na zdjęciu jest tekst: cienkie ciemne kreski ułożone w regularne wiersze.
    Śnieg, niebo czy postać na tle ściany są jasne, ale nie mają powtarzających się wierszy."""
    g = im.convert("L")
    g.thumbnail((bok, bok))
    tlo = g.filter(ImageFilter.BoxBlur(10))
    tusz = ImageChops.subtract(tlo, g).point(lambda v: 255 if v > 30 else 0)
    px = tusz.tobytes()
    n_tusz = px.count(255)
    udzial = n_tusz / max(1, len(px))
    grube = tusz.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5)).tobytes().count(255)
    cienkie = 1 - grube / max(1, n_tusz)
    okres = 0.0
    for obraz in (tusz, tusz.transpose(Image.Transpose.ROTATE_90)):  # też kartka sfotografowana bokiem
        w, h = obraz.size
        prof = obraz.resize((pasy, h), Image.Resampling.BOX).tobytes()
        for p in range(pasy):
            okres = max(okres, _okresowosc([prof[y * pasy + p] / 255 for y in range(h)]))
    siatka = tusz.resize((6, 6), Image.Resampling.BOX).tobytes()
    pokrycie = sum(1 for v in siatka if 8 <= v <= 110) / 36

    def ogr(x):
        return max(0.0, min(1.0, x))

    return round(0.5 * ogr(okres / 0.3) + 0.2 * ogr((cienkie - 0.4) / 0.4)
                 + 0.15 * ogr((pokrycie - 0.3) / 0.4) + 0.15 * ogr((udzial - 0.03) / 0.05), 3)


def _obraz_do_tekstu(sciezka: str, bok: int = 1000) -> Image.Image:
    with Image.open(sciezka) as im:
        im.draft("RGB", (bok, bok))  # JPEG: dekodowanie od razu w zmniejszonej skali
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((bok, bok))
        return im


def _analizuj_plik(w) -> tuple:
    try:
        im, rozm = miniatura(w["sciezka"])
        h = dhash(im)
        return (w["sciezka"], w["rozmiar"], w["mtime"], f"{h:016x}", ocena_dokumentu(im), ostrosc(im),
                rozm[0] if rozm else im.width, rozm[1] if rozm else im.height, None, podpis(im), None)
    except Exception as e:
        if isinstance(e, OSError) and e.errno is not None:
            raise  # błąd dostępu (np. sieć) — nie zapisujemy, spróbujemy ponownie
        return (w["sciezka"], w["rozmiar"], w["mtime"], None, None, None, None, None,
                f"{type(e).__name__}: {e}"[:200], None, None)


def analizuj(db: sqlite3.Connection, postep=None, przerwij=None, watki: int = 4) -> dict:
    """Etap 1: miniatura z nagłówka (wszystkie zdjęcia). Etap 2: tekst na większym obrazie
    (tylko jasne kandydaty na dokumenty). Liczone są tylko nowe/zmienione zdjęcia."""
    przygotuj(db)
    from .skaner import Zatwierdzanie
    zatwierdz = Zatwierdzanie(db)
    wiersze = db.execute(
        """SELECT p.sciezka, p.rozmiar, p.mtime FROM pliki p
           LEFT JOIN analiza a ON a.sciezka = p.sciezka AND a.rozmiar = p.rozmiar AND a.mtime = p.mtime
           WHERE p.rodzaj = 'zdjecie' AND (a.sciezka IS NULL OR (a.blad IS NULL AND a.podpis IS NULL))"""
    ).fetchall()

    from .stabilnosc import Straznik
    straznik = Straznik([r[0] for r in db.execute("SELECT DISTINCT korzen FROM pliki")], przerwij,
                        getattr(postep, "czeka", None))

    def zadanie(w):
        if przerwij is not None and przerwij.is_set():
            raise Przerwano(w["sciezka"])
        try:
            return straznik.wykonaj(_analizuj_plik, w["sciezka"], w)
        except Przerwano:
            raise
        except OSError:
            return None  # brak dostępu — zostaje do następnej analizy

    if postep:
        postep("analiza zdjęć", 0, len(wiersze), 0)
    with ThreadPoolExecutor(max_workers=watki) as pula:
        for i, wynik in enumerate(pula.map(zadanie, wiersze), 1):
            if wynik is None:
                continue
            db.execute("INSERT OR REPLACE INTO analiza(sciezka, rozmiar, mtime, dhash, dokument, ostrosc, szer, wys, "
                       "blad, podpis, tekst) VALUES (?,?,?,?,?,?,?,?,?,?,?)", wynik)
            zatwierdz()
            if postep and i % 20 == 0:
                postep("analiza zdjęć", i, len(wiersze), 0)
    zatwierdz(wymus=True)

    kandydaci = db.execute(
        f"""SELECT a.sciezka FROM analiza a JOIN pliki p ON {_AKTUALNE}
            WHERE a.dokument >= ? AND a.tekst IS NULL AND a.blad IS NULL""", (PROG_WSTEPNY,)).fetchall()

    def tekst(w):
        if przerwij is not None and przerwij.is_set():
            raise Przerwano(w[0])
        try:
            return w[0], ocena_tekstu(straznik.wykonaj(_obraz_do_tekstu, w[0], w[0]))
        except Przerwano:
            raise
        except Exception:
            return w[0], 0.0

    if postep:
        postep("szukanie tekstu (dokumenty)", 0, len(kandydaci), 0)
    with ThreadPoolExecutor(max_workers=watki) as pula:
        for i, (sc, t) in enumerate(pula.map(tekst, kandydaci), 1):
            db.execute("UPDATE analiza SET tekst=? WHERE sciezka=?", (t, sc))
            zatwierdz()
            if postep and i % 5 == 0:
                postep("szukanie tekstu (dokumenty)", i, len(kandydaci), 0)
    zatwierdz(wymus=True)
    grupy_podobnych(db, postep=postep)  # liczone raz, tu — potem z pamięci
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
        f"""SELECT p.rowid id, p.sciezka, p.wzgledna, p.data, COALESCE(a.tekst, 0) ocena, d.dokument decyzja
            FROM pliki p JOIN analiza a ON {_AKTUALNE}
            LEFT JOIN decyzje_dok d ON d.sciezka = p.sciezka
            WHERE p.rodzaj='zdjecie' AND (a.tekst >= ? OR d.dokument = 1)
            ORDER BY a.tekst DESC""", (PROG_KANDYDAT,)).fetchall()
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

def grupy_podobnych(db: sqlite3.Connection, prog: int = PROG_PODOBNE, postep=None) -> list[list[dict]]:
    """Grupy wizualnie podobnych zdjęć (bez grup samych identycznych plików).

    1) wstępnie: odcisk dHash różni się o ≤ prog bitów (wyszukiwanie przez pasma),
    2) potwierdzenie: podobna jasność (8×8) i kolory (4×4),
    3) grupa powstaje wokół jednego zdjęcia-wzorca — każde w grupie jest podobne do wzorca
       (bez łańcuchów A≈B≈C…, które sklejały zupełnie różne zdjęcia)."""
    przygotuj(db)
    klucz = _odcisk_danych(db, prog)
    if klucz in _PAMIEC_PODOBNYCH:
        return _PAMIEC_PODOBNYCH[klucz]
    wynik = _grupy_podobnych(db, prog, postep)
    _PAMIEC_PODOBNYCH.clear()  # pamiętamy tylko najnowszy wynik
    _PAMIEC_PODOBNYCH[klucz] = wynik
    return wynik


_PAMIEC_PODOBNYCH: dict = {}
MAKS_SASIADOW = 60  # dłuższa seria niemal jednakowych ujęć (np. timelapse) dzieli się na kilka grup — i nie
                   # porównujemy każdego z każdym (koszt rósłby z kwadratem)
MAKS_KUBELEK = 2000  # większe kubełki (setki niemal jednakowych ujęć, np. ciemne) pomijamy — koszt rośnie z kwadratem


def _odcisk_danych(db: sqlite3.Connection, prog: int) -> tuple:
    """Tani „odcisk” stanu bazy: zmienia się, gdy dochodzą/znikają zdjęcia lub wyniki analizy."""
    plik = next((r[2] for r in db.execute("PRAGMA database_list") if r[1] == "main"), "")
    a = db.execute("SELECT COUNT(*), MAX(rowid) FROM analiza").fetchone()
    p = db.execute("SELECT COUNT(*), MAX(rowid) FROM pliki").fetchone()
    o = db.execute("SELECT COUNT(pelny), MAX(rowid) FROM odciski").fetchone() if _ma_odciski(db) else (0, 0)
    return (plik or id(db), prog, *a, *p, *o)


def _grupy_podobnych(db: sqlite3.Connection, prog: int, postep=None) -> list[list[dict]]:
    odc = ", o.pelny" if _ma_odciski(db) else ", NULL pelny"
    zl = ("LEFT JOIN odciski o ON o.sciezka = p.sciezka AND o.rozmiar = p.rozmiar AND o.mtime = p.mtime"
          if _ma_odciski(db) else "")
    wiersze = [dict(w) for w in db.execute(
        f"""SELECT p.rowid id, p.sciezka, p.korzen, p.wzgledna, p.mtime, p.rozmiar, p.data,
                   a.dhash, a.ostrosc, a.szer, a.wys, a.podpis {odc}
            FROM pliki p JOIN analiza a ON {_AKTUALNE} {zl}
            WHERE p.rodzaj='zdjecie' AND a.dhash IS NOT NULL AND a.podpis IS NOT NULL""")]
    hashe = []
    for w in wiersze:
        h = int(w["dhash"], 16)
        if 6 <= h.bit_count() <= 58:  # pomijamy jednolite obrazy (czarne, białe)
            hashe.append((h, w))
    podpisy = [bytes.fromhex(w["podpis"]) for _, w in hashe]
    liczby = [h for h, _ in hashe]
    sasiedzi: dict[int, set[int]] = {}
    pasma = prog + 1
    szer = 64 // pasma
    for b in range(pasma):
        if postep:
            postep("szukanie podobnych zdjęć", b, pasma, 0)
        przes = b * szer
        maska = (1 << (szer if b < pasma - 1 else 64 - przes)) - 1
        kubelki: dict[int, list[int]] = {}
        for i, (h, _) in enumerate(hashe):
            kubelki.setdefault((h >> przes) & maska, []).append(i)
        for lista in kubelki.values():
            if len(lista) < 2 or len(lista) > MAKS_KUBELEK:
                continue
            for x in range(len(lista)):
                i = lista[x]
                hi, si = liczby[i], sasiedzi.get(i, ())
                if len(si) >= MAKS_SASIADOW:
                    continue
                for j in lista[x + 1:]:
                    if (hi ^ liczby[j]).bit_count() > prog or j in si:
                        continue
                    if len(sasiedzi.get(j, ())) >= MAKS_SASIADOW:
                        continue
                    if len(sasiedzi.get(i, ())) >= MAKS_SASIADOW:
                        break
                    szar, kol = _roznice_bajtow(podpisy[i], podpisy[j])
                    if szar <= PROG_SZAROSCI and kol <= PROG_KOLORU:
                        sasiedzi.setdefault(i, set()).add(j)
                        sasiedzi.setdefault(j, set()).add(i)
    wykorzystane: set[int] = set()
    wynik = []
    for wzor in sorted(sasiedzi, key=lambda i: -len(sasiedzi[i])):
        if wzor in wykorzystane:
            continue
        czlonkowie = [wzor] + [j for j in sasiedzi[wzor] if j not in wykorzystane]
        if len(czlonkowie) < 2:
            continue
        g = [hashe[i][1] for i in czlonkowie]
        pelne = {w["pelny"] for w in g}
        if len(pelne) == 1 and None not in pelne:
            continue  # same identyczne — to zakładka „Duplikaty”
        wykorzystane.update(czlonkowie)
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
