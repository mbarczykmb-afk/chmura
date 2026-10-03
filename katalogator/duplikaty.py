"""Wykrywanie duplikatów po zawartości i bezpieczne odkładanie ich na bok (z cofaniem).

Etapy (każdy odsiewa kandydatów, żeby jak najmniej czytać przez sieć):
1. ten sam rozmiar (z bazy skanu, bez czytania plików),
2. szybki odcisk: 1 MB z początku + 1 MB z końca,
3. pełny odcisk całej zawartości (BLAKE2b) — dopiero on decyduje o duplikacie.
Odciski są zapamiętywane w bazie, więc ponowne wyszukiwanie jest natychmiastowe.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import indeks
from .skaner import Przerwano, Zatwierdzanie
from .stabilnosc import opis_bledu, tylko_w_chmurze

BLOK = 1 << 20
# Pełny odcisk dużych plików liczymy po jednym naraz: kilka równoległych długich odczytów z jednego dysku
# (zwłaszcza sieciowego z talerzem, np. WD My Cloud) to skakanie głowicy i wielokrotnie wolniejszy odczyt.
DUZY_PLIK = 64 * BLOK
FOLDER_ODLOZONE = "Odłożone"   # <korzeń>/Odłożone/{Duplikaty,Podobne,Nieostre}/<ścieżka>
PODFOLDERY = {"duplikat": "Duplikaty", "podobne": "Podobne", "nieostre": "Nieostre", "smieci": "Śmieci",
              "usuniete": "Usunięte"}
FOLDER_DUPLIKATOW = "_Duplikaty_Katalogator"  # do wersji 1.3 — nadal pomijany przy skanie

SCHEMAT = """
CREATE TABLE IF NOT EXISTS odciski (
    sciezka TEXT PRIMARY KEY,
    rozmiar INTEGER NOT NULL,
    mtime   REAL NOT NULL,
    szybki  TEXT,
    pelny   TEXT
);
CREATE INDEX IF NOT EXISTS ix_odciski_pelny ON odciski(pelny);
CREATE TABLE IF NOT EXISTS operacje (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    partia  INTEGER NOT NULL,
    czas    REAL NOT NULL,
    typ     TEXT NOT NULL,
    z_      TEXT NOT NULL,
    do_     TEXT NOT NULL,
    wiersz  TEXT NOT NULL,
    cofnieta INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS dup_meta (klucz TEXT PRIMARY KEY, wartosc TEXT);
CREATE TABLE IF NOT EXISTS dup_przejrzane (rodzaj TEXT NOT NULL, klucz TEXT NOT NULL, PRIMARY KEY (rodzaj, klucz));
"""

# Ścieżki, które zwykle są kopiami — plik z nich zostawiamy tylko w ostateczności.
_PODEJRZANE = re.compile(
    r"kopia|copy|duplikat|backup|kopie zapasowe|whatsapp|messenger|download|pobrane|"
    r"temp\b|tmp\b|\(\d+\)|odłożone|" + FOLDER_DUPLIKATOW.lower(),
    re.IGNORECASE,
)


def przygotuj(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMAT)


def nowa_partia(db: sqlite3.Connection) -> int:
    """Numer operacji (czas w ms) — zawsze większy od poprzedniego, także przy dwóch operacjach w tej samej ms."""
    ost = db.execute("SELECT MAX(partia) FROM operacje").fetchone()[0] or 0
    return max(int(time.time() * 1000), ost + 1)


def _odcisk(sciezka: str, rozmiar: int, pelny: bool, przerwij=None, licz=None) -> str:
    h = hashlib.blake2b(digest_size=20)
    h.update(str(rozmiar).encode())
    with open(sciezka, "rb") as f:
        if pelny:
            while True:
                if przerwij is not None and przerwij.is_set():
                    raise Przerwano(sciezka)
                kawalek = f.read(4 * BLOK)
                if not kawalek:
                    break
                h.update(kawalek)
                if licz is not None:
                    licz(len(kawalek))
        else:
            h.update(f.read(BLOK))
            if rozmiar > 2 * BLOK:
                f.seek(-BLOK, os.SEEK_END)
                h.update(f.read(BLOK))
            if licz is not None:
                licz(min(rozmiar, 2 * BLOK))
    return h.hexdigest()


def szukaj(db: sqlite3.Connection, postep=None, przerwij=None, watki: int = 4) -> dict:
    """postep(etap, zrobione, wszystkie, bajty). Zwraca podsumowanie()."""
    przygotuj(db)
    from .stabilnosc import Straznik
    straznik = Straznik([r[0] for r in db.execute("SELECT DISTINCT korzen FROM pliki")], przerwij,
                        getattr(postep, "czeka", None))
    bajty = [0]
    razem = [0]
    biezacy = {"etap": "", "zrobione": 0, "wszystkie": 0, "t": 0.0, "plik": ""}
    jeden_duzy = threading.Lock()
    problemy = {"chmura": 0, "bledy": 0, "przyklad": ""}  # pliki pominięte — widać je w oknie

    def opis_problemow() -> str:
        t = []
        if problemy["chmura"]:
            t.append(f"{problemy['chmura']} plików tylko w chmurze (pominięte)")
        if problemy["bledy"]:
            t.append(f"nie da się odczytać {problemy['bledy']} plików — np. {problemy['przyklad']}")
        return "; ".join(t)

    def dod():
        d = {"bajty_razem": razem[0], **({"plik": biezacy["plik"]} if biezacy["plik"] else {})}
        if problemy["chmura"] or problemy["bledy"]:
            d["opis"] = "⚠ " + opis_problemow()
        return d

    def licz(n):  # wołane w trakcie czytania — pasek rusza się także przy jednym wielkim pliku
        bajty[0] += n
        teraz = time.monotonic()
        if postep is not None and teraz - biezacy["t"] > 0.5:
            biezacy["t"] = teraz
            postep(biezacy["etap"], biezacy["zrobione"], biezacy["wszystkie"], bajty[0], **dod())

    def zglos(etap, zrobione, wszystkie):
        biezacy.update(etap=etap, zrobione=zrobione, wszystkie=wszystkie)
        if postep is not None:
            postep(etap, zrobione, wszystkie, bajty[0], **dod())

    def policz(etap: str, wiersze: list, pelny: bool) -> None:
        kol = "pelny" if pelny else "szybki"
        bajty[0] = 0
        razem[0] = sum(w["rozmiar"] if pelny else min(w["rozmiar"], 2 * BLOK) for w in wiersze)
        zglos(etap, 0, len(wiersze))

        # wspólny indeks: odcisk policzony wcześniej (inny tryb / projekt) — bez czytania pliku
        gotowe = {s: r[kol] for s, r in indeks.pobierz("odciski", [(w["sciezka"], w["rozmiar"], w["mtime"])
                                                                   for w in wiersze]).items() if r[kol]}

        def zadanie(w):
            if przerwij is not None and przerwij.is_set():
                raise Przerwano(w["sciezka"])
            if w["sciezka"] in gotowe:
                return w, gotowe[w["sciezka"]]
            if tylko_w_chmurze(w["sciezka"]):  # otwarcie ściągałoby plik z internetu (albo kończyło się błędem)
                problemy["chmura"] += 1
                return w, None
            try:
                if pelny and w["rozmiar"] >= DUZY_PLIK:
                    with jeden_duzy:  # duże pliki po kolei — odczyt ciągły zamiast skakania po dysku
                        if przerwij is not None and przerwij.is_set():
                            raise Przerwano(w["sciezka"])
                        biezacy["plik"] = w["sciezka"]
                        try:
                            return w, straznik.wykonaj(_odcisk, w["sciezka"], w["sciezka"], w["rozmiar"], True,
                                                       przerwij, licz)
                        finally:
                            biezacy["plik"] = ""
                return w, straznik.wykonaj(_odcisk, w["sciezka"], w["sciezka"], w["rozmiar"], pelny, przerwij, licz)
            except Przerwano:
                raise
            except OSError as e:  # plik zniknął / brak dostępu — pomijamy, ale widać to w oknie
                problemy["bledy"] += 1
                if not problemy["przyklad"]:
                    problemy["przyklad"] = f"„{os.path.basename(w['sciezka'])}”: {opis_bledu(e)}"
                return w, None

        zatwierdz = Zatwierdzanie(db)
        nowe_do_indeksu: list = []
        with ThreadPoolExecutor(max_workers=watki) as pula:
            for i, (w, odc) in enumerate(pula.map(zadanie, wiersze), 1):
                if odc is not None:
                    db.execute(
                        "INSERT INTO odciski(sciezka, rozmiar, mtime) VALUES (?,?,?) "
                        "ON CONFLICT(sciezka) DO UPDATE SET rozmiar=excluded.rozmiar, mtime=excluded.mtime, "
                        "szybki=CASE WHEN odciski.rozmiar=excluded.rozmiar AND odciski.mtime=excluded.mtime "
                        "THEN odciski.szybki END, pelny=CASE WHEN odciski.rozmiar=excluded.rozmiar "
                        "AND odciski.mtime=excluded.mtime THEN odciski.pelny END",
                        (w["sciezka"], w["rozmiar"], w["mtime"]),
                    )
                    db.execute(f"UPDATE odciski SET {kol}=? WHERE sciezka=?", (odc, w["sciezka"]))
                    if w["sciezka"] not in gotowe:
                        nowe_do_indeksu.append((w, odc))
                    # mały plik przeczytany w całości: szybki odcisk = pełny
                    if not pelny and w["rozmiar"] <= 2 * BLOK:
                        db.execute("UPDATE odciski SET pelny=? WHERE sciezka=?", (odc, w["sciezka"]))
                zatwierdz(wymus=pelny)  # pełny odcisk dużego pliku trwa długo — zapisuj od razu
                if i % 20 == 0:
                    zglos(etap, i, len(wiersze))
        db.commit()
        if nowe_do_indeksu and indeks.wlaczony():
            znane = indeks.pobierz("odciski", [(w["sciezka"], w["rozmiar"], w["mtime"]) for w, _ in nowe_do_indeksu])
            wpisy = []
            for w, odc in nowe_do_indeksu:
                stare = znane.get(w["sciezka"], {})
                d = {"sciezka": w["sciezka"], "rozmiar": w["rozmiar"], "mtime": w["mtime"],
                     "szybki": stare.get("szybki"), "pelny": stare.get("pelny")}
                d[kol] = odc
                if not pelny and w["rozmiar"] <= 2 * BLOK:
                    d["pelny"] = odc  # mały plik przeczytany w całości
                wpisy.append(d)
            indeks.zapisz("odciski", wpisy)
        zglos(etap, len(wiersze), len(wiersze))

    aktualny = "o.rozmiar = p.rozmiar AND o.mtime = p.mtime"
    try:
        # 1+2: pliki o powtarzającym się rozmiarze, bez aktualnego szybkiego odcisku
        brak_szybkiego = db.execute(
            f"""SELECT p.sciezka, p.rozmiar, p.mtime FROM pliki p
                LEFT JOIN odciski o ON o.sciezka = p.sciezka AND {aktualny}
                WHERE p.rozmiar > 0 AND o.szybki IS NULL AND p.rozmiar IN
                  (SELECT rozmiar FROM pliki WHERE rozmiar > 0 GROUP BY rozmiar HAVING COUNT(*) > 1)"""
        ).fetchall()
        policz("szybkie porównanie", brak_szybkiego, pelny=False)
        # 3: pełny odcisk tylko tam, gdzie szybki się powtarza
        brak_pelnego = db.execute(
            f"""SELECT p.sciezka, p.rozmiar, p.mtime FROM pliki p
                JOIN odciski o ON o.sciezka = p.sciezka AND {aktualny}
                WHERE o.pelny IS NULL AND (p.rozmiar, o.szybki) IN
                  (SELECT p2.rozmiar, o2.szybki FROM pliki p2
                   JOIN odciski o2 ON o2.sciezka = p2.sciezka AND o2.rozmiar = p2.rozmiar AND o2.mtime = p2.mtime
                   WHERE o2.szybki IS NOT NULL GROUP BY p2.rozmiar, o2.szybki HAVING COUNT(*) > 1)
                ORDER BY p.rozmiar"""
        ).fetchall()
        policz("dokładne sprawdzanie", brak_pelnego, pelny=True)
        # zapamiętaj, że szukano (także gdy nic nie znaleziono — okno pokaże „brak duplikatów”, nie „nie szukano”)
        db.execute("INSERT OR REPLACE INTO dup_meta VALUES ('ostatnie_szukanie', ?)", (str(time.time()),))
    finally:
        db.commit()
    return {**podsumowanie(db), "problemy": opis_problemow()}


def szukano(db: sqlite3.Connection) -> bool:
    przygotuj(db)
    return db.execute("SELECT 1 FROM dup_meta WHERE klucz='ostatnie_szukanie'").fetchone() is not None \
        or db.execute("SELECT 1 FROM odciski LIMIT 1").fetchone() is not None


_GRUPY = """
    SELECT o.pelny h, p.rozmiar, COUNT(*) n, MIN(p.rodzaj) rodzaj FROM pliki p
    JOIN odciski o ON o.sciezka = p.sciezka AND o.rozmiar = p.rozmiar AND o.mtime = p.mtime
    WHERE o.pelny IS NOT NULL
    GROUP BY o.pelny HAVING COUNT(*) > 1
"""


# „Zostaw wszystkie” po przejrzeniu: grupa znika z listy (duplikaty: klucz = odcisk, podobne: ścieżki grupy)
def oznacz_przejrzane(db: sqlite3.Connection, rodzaj: str, klucze: list[str], wartosc: bool = True) -> dict:
    przygotuj(db)
    if wartosc:
        db.executemany("INSERT OR IGNORE INTO dup_przejrzane VALUES (?, ?)", [(rodzaj, str(k)) for k in klucze])
    elif klucze:
        db.executemany("DELETE FROM dup_przejrzane WHERE rodzaj=? AND klucz=?", [(rodzaj, str(k)) for k in klucze])
    else:
        db.execute("DELETE FROM dup_przejrzane WHERE rodzaj=?", (rodzaj,))
    db.commit()
    return {"przejrzane": ile_przejrzanych(db, rodzaj)}


def ile_przejrzanych(db: sqlite3.Connection, rodzaj: str) -> int:
    przygotuj(db)
    return db.execute("SELECT COUNT(*) FROM dup_przejrzane WHERE rodzaj=?", (rodzaj,)).fetchone()[0]


def przejrzane_klucze(db: sqlite3.Connection, rodzaj: str) -> set[str]:
    przygotuj(db)
    return {r[0] for r in db.execute("SELECT klucz FROM dup_przejrzane WHERE rodzaj=?", (rodzaj,))}


def podsumowanie(db: sqlite3.Connection) -> dict:
    """Z pamiętanej listy grup (ta sama, co lista w zakładce) — bez osobnego, drogiego zapytania."""
    przygotuj(db)
    pomin = przejrzane_klucze(db, "dup")
    grupy_ = [g for g in _naglowki(db) if g[0] not in pomin]
    rodzaje: dict[str, int] = {}
    for g in grupy_:
        rodzaje[g[3]] = rodzaje.get(g[3], 0) + 1
    return {"grupy": len(grupy_), "nadmiar": sum(g[2] - 1 for g in grupy_),
            "bajty": sum((g[2] - 1) * g[1] for g in grupy_), "rodzaje": rodzaje}


def _ocena(plik: dict, cele: set[str]) -> tuple:
    """Mniejsza = lepszy kandydat do ZOSTAWIENIA."""
    podejrzana = len(_PODEJRZANE.findall(plik["wzgledna"]))
    w_celu = 0 if plik["korzen"] in cele else 1  # to, co już jest w miejscu docelowym, zostaje
    return (podejrzana, w_celu, plik["mtime"], len(plik["wzgledna"]), plik["wzgledna"])


# Lista grup duplikatów (h, rozmiar, n, rodzaj), od największego zysku — przy 400 tys. plików liczy się sekundy,
# więc jest pamiętana; po odłożeniu / cofnięciu poprawiamy tylko zmienione grupy (bez liczenia wszystkiego od nowa).
_PAMIEC_GRUP: dict = {}


def _odcisk_stanu(db: sqlite3.Connection) -> tuple:
    """Tani „odcisk” plików i odcisków — zmienia się po skanie, szukaniu, odłożeniu i porządkowaniu."""
    plik = next((r[2] for r in db.execute("PRAGMA database_list") if r[1] == "main"), "")
    return (plik or id(db),
            *db.execute("SELECT COUNT(*), MAX(rowid), TOTAL(rowid), TOTAL(mtime), TOTAL(rozmiar) FROM pliki").fetchone(),
            *db.execute("SELECT COUNT(*), TOTAL(rowid), COUNT(pelny), MAX(pelny), MIN(pelny) FROM odciski").fetchone())


def _kolejnosc(g) -> tuple:
    return (-(g[2] - 1) * g[1], g[0])


def _naglowki(db: sqlite3.Connection) -> list[tuple]:
    klucz = _odcisk_stanu(db)
    if _PAMIEC_GRUP.get("klucz") != klucz:
        naglowki = sorted((tuple(r) for r in db.execute(f"SELECT h, rozmiar, n, rodzaj FROM ({_GRUPY})")),
                          key=_kolejnosc)
        _PAMIEC_GRUP.clear()
        _PAMIEC_GRUP.update(klucz=klucz, naglowki=naglowki)
    return _PAMIEC_GRUP["naglowki"]


def _aktualna_pamiec(db: sqlite3.Connection) -> bool:
    return bool(_PAMIEC_GRUP) and _PAMIEC_GRUP.get("klucz") == _odcisk_stanu(db)


def _popraw_pamiec(db: sqlite3.Connection, odciski: set, byla_aktualna: bool) -> None:
    """Po odłożeniu / cofnięciu: przelicz tylko grupy o tych odciskach (zamiast całej listy)."""
    if not byla_aktualna or not odciski:
        return
    nowe = {g[0]: g for g in _PAMIEC_GRUP["naglowki"] if g[0] not in odciski}
    for h in odciski:
        r = db.execute("""SELECT p.rozmiar, COUNT(*) n, MIN(p.rodzaj) FROM pliki p
                          JOIN odciski o ON o.sciezka = p.sciezka AND o.rozmiar = p.rozmiar AND o.mtime = p.mtime
                          WHERE o.pelny = ?""", (h,)).fetchone()
        if r and r[1] > 1:
            nowe[h] = (h, r[0], r[1], r[2])
    _PAMIEC_GRUP.update(klucz=_odcisk_stanu(db), naglowki=sorted(nowe.values(), key=_kolejnosc))


def _odciski_plikow(db: sqlite3.Connection, ids) -> set:
    ids = [int(i) for i in ids]
    if not ids:
        return set()
    return {r[0] for r in db.execute(
        f"SELECT o.pelny FROM odciski o JOIN pliki p ON p.sciezka = o.sciezka WHERE o.pelny IS NOT NULL "
        f"AND p.rowid IN ({','.join('?' * len(ids))})", ids)}


def odciski_wg_id(db: sqlite3.Connection, ids) -> dict[int, str]:
    """{id pliku: pełny odcisk} — tylko aktualne odciski (plik nie zmienił się od sprawdzenia)."""
    ids = [int(i) for i in ids]
    wynik: dict[int, str] = {}
    for c in range(0, len(ids), 500):
        cz = ids[c:c + 500]
        for r in db.execute(
                f"""SELECT p.rowid, o.pelny FROM pliki p JOIN odciski o ON o.sciezka = p.sciezka
                    AND o.rozmiar = p.rozmiar AND o.mtime = p.mtime
                    WHERE o.pelny IS NOT NULL AND p.rowid IN ({','.join('?' * len(cz))})""", cz):
            wynik[r[0]] = r[1]
    return wynik


def zwin_kopie(db: sqlite3.Connection, pozycje: list[dict]) -> list[dict]:
    """Identyczne pliki na liście (Dokumenty, Nie z aparatu) — jedna karta z listą kopii („kopie”: [id…]);
    decyzja dla karty dotyczy wszystkich kopii."""
    przygotuj(db)
    odc = odciski_wg_id(db, [p["id"] for p in pozycje])
    pierwszy: dict[str, dict] = {}
    wynik = []
    for p in pozycje:
        h = odc.get(p["id"])
        if h and h in pierwszy:
            pierwszy[h].setdefault("kopie", []).append(p["id"])
            continue
        if h:
            pierwszy[h] = p
        wynik.append(p)
    return wynik


def grupy(db: sqlite3.Connection, rodzaj: str | None = None, od: int = 0, ile: int = 50,
          cele: set[str] | None = None) -> list[dict]:
    przygotuj(db)
    cele = cele or set()
    pomin = przejrzane_klucze(db, "dup")
    lista = [g for g in _naglowki(db) if g[0] not in pomin and (not rodzaj or g[3] == rodzaj)]
    wynik = []
    for h, rozmiar, n, _ in lista[od:od + ile]:
        pliki = [dict(r) for r in db.execute(
            """SELECT p.rowid id, p.sciezka, p.korzen, p.wzgledna, p.mtime, p.data, p.rodzaj
               FROM pliki p JOIN odciski o ON o.sciezka = p.sciezka AND o.rozmiar = p.rozmiar AND o.mtime = p.mtime
               WHERE o.pelny = ?""", (h,))]
        if len(pliki) < 2:
            continue
        pliki.sort(key=lambda p: _ocena(p, cele))
        wynik.append({
            "h": h, "rozmiar": rozmiar, "n": len(pliki), "rodzaj": pliki[0]["rodzaj"],
            "zostaw": pliki[0]["id"], "pliki": pliki,
        })
    return wynik


def etykieta_korzenia(korzen: str) -> str:
    """Nazwa podfolderu dla plików z danego źródła w jednym wspólnym koszu: Y:\\ → „Y”,
    Z:\\mbarczykmb → „Z - mbarczykmb”, \\\\serwer\\zdjecia → „serwer - zdjecia”."""
    czesci = [c for c in re.split(r"[\\/]+", korzen.replace(":", "")) if c]
    return " - ".join(czesci) or "folder"


def ustaw_kosz(db: sqlite3.Connection, docelowy: str | None) -> None:
    """Wspólny kosz w miejscu docelowym (<cel>/Odłożone/…) — albo None: kosz w każdym folderze źródłowym."""
    przygotuj(db)
    if docelowy:
        db.execute("INSERT OR REPLACE INTO dup_meta VALUES ('kosz_docelowy', ?)", (docelowy,))
    else:
        db.execute("DELETE FROM dup_meta WHERE klucz='kosz_docelowy'")
    db.commit()


def kosz_docelowy(db: sqlite3.Connection) -> str | None:
    """Miejsce docelowe z koszem — tylko gdy jest dostępne (dysk sieciowy odłączony: kosz w źródle)."""
    try:
        r = db.execute("SELECT wartosc FROM dup_meta WHERE klucz='kosz_docelowy'").fetchone()
    except sqlite3.OperationalError:
        return None
    return r[0] if r and r[0] and os.path.isdir(r[0]) else None


def _cel_przeniesienia(korzen: str, wzgledna: str, typ: str = "duplikat", docelowy: str | None = None) -> str:
    """<korzeń>/Odłożone/<typ>/<ścieżka> — albo, przy wspólnym koszu, <cel>/Odłożone/<typ>/<źródło>/<ścieżka>."""
    if docelowy:
        zrodlo = "" if os.path.normcase(os.path.normpath(korzen)) == os.path.normcase(os.path.normpath(docelowy)) \
            else etykieta_korzenia(korzen)  # pliki z samej biblioteki — bez podfolderu źródła
        cel = os.path.join(docelowy, FOLDER_ODLOZONE, PODFOLDERY.get(typ, "Inne"), zrodlo, wzgledna)
    else:
        cel = os.path.join(korzen, FOLDER_ODLOZONE, PODFOLDERY.get(typ, "Inne"), wzgledna)
    baza, ext = os.path.splitext(cel)
    i = 2
    while os.path.exists(cel):
        cel = f"{baza} ({i}){ext}"
        i += 1
    return cel


def przenies_plik(z: str, do: str) -> None:
    """Przeniesienie pliku — także między dyskami (Y: → Z:): kopia, sprawdzenie rozmiaru, usunięcie oryginału."""
    from . import sprzatanie
    sprzatanie.zmiana_odlozonych()  # licznik kosza policzy się od nowa
    os.makedirs(os.path.dirname(do), exist_ok=True)
    try:
        os.rename(z, do)
        return
    except OSError as e:
        if not (getattr(e, "winerror", None) == 17 or e.errno == 18):  # inny dysk (Windows / EXDEV)
            raise
    tmp = do + ".katalogator-tmp"
    try:
        shutil.copy2(z, tmp)
        if os.path.getsize(tmp) != os.path.getsize(z):
            raise OSError("kopia niepełna")
        os.replace(tmp, do)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    os.remove(z)


def przenies(db: sqlite3.Connection, decyzje: list[dict]) -> dict:
    """decyzje: [{"zostaw": id, "usun": [id, ...]}]. Przenosi do <korzeń>/Odłożone/Duplikaty/
    (przy wspólnym koszu: <miejsce docelowe>/Odłożone/Duplikaty/<źródło>/)."""
    przygotuj(db)
    partia = nowa_partia(db)
    docelowy = kosz_docelowy(db)
    przeniesione, pominiete, bajty = 0, [], 0
    aktualna = _aktualna_pamiec(db)
    zmienione = _odciski_plikow(db, [i for d in decyzje for i in d.get("usun", [])]) if aktualna else set()
    for d in decyzje:
        ids = [d["zostaw"], *d.get("usun", [])]
        if d["zostaw"] in d.get("usun", []) or not d.get("usun"):
            continue
        wiersze = {r["rowid"]: r for r in db.execute(
            f"SELECT rowid, * FROM pliki WHERE rowid IN ({','.join('?' * len(ids))})", ids)}
        if len(wiersze) != len(set(ids)):
            pominiete.append("Grupa nieaktualna — przeskanuj ponownie.")
            continue
        odciski = [r[0] for r in db.execute(
            f"SELECT o.pelny FROM odciski o JOIN pliki p ON p.sciezka=o.sciezka AND o.rozmiar=p.rozmiar "
            f"AND o.mtime=p.mtime WHERE p.rowid IN ({','.join('?' * len(ids))})", ids)]
        # każdy plik musi mieć aktualny pełny odcisk i wszystkie muszą być równe
        if len(odciski) != len(set(ids)) or None in odciski or len(set(odciski)) != 1:
            pominiete.append("Pliki w grupie nie są identyczne — pominięto.")
            continue
        zostaw = wiersze[d["zostaw"]]
        try:
            st = os.stat(zostaw["sciezka"])
            if st.st_size != zostaw["rozmiar"]:
                raise OSError("zmieniony")
        except OSError:
            pominiete.append(f"Nie ma pliku do zostawienia: {zostaw['wzgledna']}")
            continue
        for i in d["usun"]:
            try:  # ten sam plik widziany dwa razy (ten sam folder pod dwiema nazwami) — to nie kopia
                if os.path.samefile(zostaw["sciezka"], wiersze[i]["sciezka"]):
                    pominiete.append(f"To ten sam plik (ten sam folder dodany dwa razy?): {wiersze[i]['wzgledna']}")
                    continue
            except OSError:
                pass
            blad = _odloz_wiersz(db, wiersze[i], partia, "duplikat", docelowy)
            if blad:
                pominiete.append(blad)
            else:
                przeniesione += 1
                bajty += wiersze[i]["rozmiar"]
        db.commit()
    _popraw_pamiec(db, zmienione, aktualna)
    return {"przeniesione": przeniesione, "bajty": bajty, "pominiete": pominiete, "partia": partia}


def _odloz_wiersz(db: sqlite3.Connection, w, partia: int, typ: str, docelowy: str | None = None) -> str | None:
    """Przenosi plik do <korzeń>/Odłożone/<Duplikaty|Podobne|Nieostre>/<ścieżka>. Zwraca opis błędu albo None."""
    try:
        st = os.stat(w["sciezka"])
        if (st.st_size, st.st_mtime) != (w["rozmiar"], w["mtime"]):
            return f"Zmieniony od skanu: {w['wzgledna']}"
        cel = _cel_przeniesienia(w["korzen"], w["wzgledna"], typ, docelowy)
        przenies_plik(w["sciezka"], cel)
    except OSError as e:
        return f"{w['wzgledna']}: {e.strerror or e}"
    dane = {k: w[k] for k in w.keys() if k != "rowid"}
    dane["_rowid"] = w["rowid"]  # przy cofaniu plik wraca z tym samym numerem (miniatury, propozycja drzewa)
    db.execute("INSERT INTO operacje(partia, czas, typ, z_, do_, wiersz) VALUES (?,?,?,?,?,?)",
               (partia, time.time(), typ, w["sciezka"], cel, json.dumps(dane, ensure_ascii=False)))
    db.execute("DELETE FROM pliki WHERE rowid = ?", (w["rowid"],))
    # zapis po każdym pliku: przenoszenie setek plików po sieci trwa minuty, a otwarta transakcja blokowała
    # w tym czasie każde kliknięcie w oknie („database is locked”); plik już przeniesiony = wpis od razu trwały
    db.commit()
    return None


def odloz(db: sqlite3.Connection, ids: list[int], typ: str) -> dict:
    """Odkłada wskazane pliki (np. podobne / nieostre zdjęcia) — bez wymogu identyczności."""
    przygotuj(db)
    partia = nowa_partia(db)
    przeniesione, pominiete, bajty = 0, [], 0
    docelowy = kosz_docelowy(db)
    aktualna = _aktualna_pamiec(db)
    zmienione = _odciski_plikow(db, ids) if aktualna else set()
    for i in dict.fromkeys(int(x) for x in ids):
        w = db.execute("SELECT rowid, * FROM pliki WHERE rowid=?", (i,)).fetchone()
        if not w:
            pominiete.append("Plik nieaktualny — przeskanuj ponownie.")
            continue
        blad = _odloz_wiersz(db, w, partia, typ, docelowy)
        if blad:
            pominiete.append(blad)
        else:
            przeniesione += 1
            bajty += w["rozmiar"]
    db.commit()
    _popraw_pamiec(db, zmienione, aktualna)
    return {"przeniesione": przeniesione, "bajty": bajty, "pominiete": pominiete, "partia": partia}


def ostatnia_partia(db: sqlite3.Connection) -> dict | None:
    przygotuj(db)
    r = db.execute(
        "SELECT partia, COUNT(*) n, MIN(czas) czas, MIN(typ) typ FROM operacje WHERE cofnieta = 0 "
        "GROUP BY partia ORDER BY partia DESC LIMIT 1").fetchone()
    return dict(r) if r else None


def cofnij(db: sqlite3.Connection, partia: int | None = None) -> dict:
    """Przywraca pliki z ostatniej nie cofniętej operacji (albo ze wskazanej partii)."""
    ost = ostatnia_partia(db) if partia is None else {"partia": int(partia)}
    if not ost:
        return {"przywrocone": 0, "bledy": []}
    przywrocone, bledy = 0, []
    aktualna = _aktualna_pamiec(db)
    for op in db.execute("SELECT * FROM operacje WHERE partia = ? AND cofnieta = 0", (ost["partia"],)).fetchall():
        try:
            if os.path.exists(op["z_"]):
                raise OSError(f"w miejscu oryginału jest już plik: {op['z_']}")
            przenies_plik(op["do_"], op["z_"])
        except OSError as e:
            bledy.append(str(e))
            continue
        w = json.loads(op["wiersz"])
        rowid = w.pop("_rowid", None)
        if rowid is not None and not db.execute("SELECT 1 FROM pliki WHERE rowid=?", (rowid,)).fetchone():
            w["rowid"] = rowid
        db.execute(f"INSERT OR REPLACE INTO pliki({','.join(w)}) VALUES ({','.join('?' * len(w))})", list(w.values()))
        db.execute("UPDATE operacje SET cofnieta = 1 WHERE id = ?", (op["id"],))
        db.commit()  # jak przy odkładaniu — bez długiej blokady bazy
        przywrocone += 1
    db.commit()
    if aktualna:  # przywrócone pliki wracają do swoich grup
        przywr = [r[0] for r in db.execute("SELECT z_ FROM operacje WHERE partia=? AND cofnieta=1", (ost["partia"],))]
        hs = {r[0] for c in range(0, len(przywr), 500) for r in db.execute(
            f"SELECT pelny FROM odciski WHERE pelny IS NOT NULL AND sciezka IN ({','.join('?' * len(przywr[c:c + 500]))})",
            przywr[c:c + 500])}
        _popraw_pamiec(db, hs, True)
    _usun_puste(db, ost["partia"])
    return {"przywrocone": przywrocone, "bledy": bledy, "partia": ost["partia"]}


def _usun_puste(db: sqlite3.Connection, partia: int) -> None:
    """Sprząta puste podfoldery w Odłożone (i dawnym _Duplikaty_Katalogator) po cofnięciu."""
    granice = (FOLDER_ODLOZONE, FOLDER_DUPLIKATOW)
    for (do_,) in db.execute("SELECT do_ FROM operacje WHERE partia = ?", (partia,)):
        folder = os.path.dirname(do_)
        while any(g in folder for g in granice):
            try:
                os.rmdir(folder)
            except OSError:
                break
            if os.path.basename(folder) in granice:
                break
            folder = os.path.dirname(folder)
