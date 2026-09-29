"""Wykonanie planu: kopiowanie / przenoszenie z weryfikacją, dziennikiem i cofaniem.

Zasady bezpieczeństwa:
- kopia powstaje najpierw jako plik tymczasowy, potem jest sprawdzana sumą kontrolną
  i dopiero wtedy dostaje docelową nazwę;
- przy przenoszeniu oryginał znika dopiero po udanej weryfikacji kopii
  (na tym samym dysku — szybka zmiana nazwy bez kopiowania);
- nic nie jest nadpisywane: zajęta nazwa dostaje dopisek „ (2)”;
- każda operacja trafia do dziennika i można ją cofnąć.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import time

from . import planista, typy
from .skaner import Przerwano

SCHEMAT = """
CREATE TABLE IF NOT EXISTS wykonanie (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    partia   INTEGER NOT NULL,
    plan_id  INTEGER NOT NULL,
    zrodlo   TEXT NOT NULL,
    cel      TEXT NOT NULL,
    tryb     TEXT NOT NULL,
    usuniete INTEGER NOT NULL DEFAULT 0,
    rozmiar  INTEGER NOT NULL,
    mtime    REAL NOT NULL,
    czas     REAL NOT NULL,
    cofniete INTEGER NOT NULL DEFAULT 0
);
"""
BLOK = 4 << 20
TMP = ".katalogator-tmp"


def przygotuj(db: sqlite3.Connection) -> None:
    planista.przygotuj(db)
    db.executescript(SCHEMAT)


def _wolumin(sciezka: str) -> str:
    d, _ = os.path.splitdrive(os.path.abspath(sciezka))
    if d:
        return d.lower()
    try:
        return str(os.stat(sciezka).st_dev)
    except OSError:
        return ""


def ten_sam_wolumin(a: str, b_folder: str) -> bool:
    b = b_folder
    while b and not os.path.exists(b):
        nb = os.path.dirname(b)
        if nb == b:
            break
        b = nb
    wa, wb = _wolumin(a), _wolumin(b)
    return bool(wa) and wa == wb


def _hash(sciezka: str, przerwij=None, licz=None) -> str:
    h = hashlib.blake2b(digest_size=20)
    with open(sciezka, "rb") as f:
        while True:
            if przerwij is not None and przerwij.is_set():
                raise Przerwano(sciezka)
            k = f.read(BLOK)
            if not k:
                return h.hexdigest()
            h.update(k)
            if licz:
                licz(len(k))


def kopiuj_z_weryfikacja(zrodlo: str, cel: str, przerwij=None, licz=None) -> None:
    """Kopiuje do pliku tymczasowego, liczy sumę w locie, weryfikuje kopię i nadaje nazwę."""
    tmp = cel + TMP
    h = hashlib.blake2b(digest_size=20)
    try:
        with open(zrodlo, "rb") as fz, open(tmp, "wb") as fc:
            while True:
                if przerwij is not None and przerwij.is_set():
                    raise Przerwano(zrodlo)
                k = fz.read(BLOK)
                if not k:
                    break
                h.update(k)
                fc.write(k)
                if licz:
                    licz(len(k))
            fc.flush()
            os.fsync(fc.fileno())
        if _hash(tmp, przerwij) != h.hexdigest():
            raise OSError("kopia różni się od oryginału (błąd zapisu lub sieci)")
        shutil.copystat(zrodlo, tmp)
        if os.path.exists(cel):
            raise FileExistsError(cel)
        os.replace(tmp, cel)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _wolna(cel: str) -> str:
    if not os.path.exists(cel):
        return cel
    baza, ext = os.path.splitext(cel)
    i = 2
    while os.path.exists(f"{baza} ({i}){ext}"):
        i += 1
    return f"{baza} ({i}){ext}"


def do_zrobienia(db: sqlite3.Connection) -> list[sqlite3.Row]:
    przygotuj(db)
    return db.execute(
        "SELECT * FROM plan WHERE tryb IN ('kopiuj','przenies') AND pominiety=0 AND stan='nowy' "
        "AND (wynik IS NULL OR wynik LIKE 'blad%') ORDER BY id").fetchall()


def sprawdz(db: sqlite3.Connection) -> dict:
    """Ile trzeba skopiować i czy starczy miejsca."""
    wiersze = do_zrobienia(db)
    cel = planista.meta(db).get("cel", "")
    potrzeba = sum(w["rozmiar"] for w in wiersze
                   if w["tryb"] == "kopiuj" or not ten_sam_wolumin(w["sciezka"], cel))
    try:
        os.makedirs(cel, exist_ok=True)
        wolne = shutil.disk_usage(cel).free
    except OSError as e:
        return {"blad": f"Brak dostępu do miejsca docelowego: {e.strerror or e}", "plikow": len(wiersze)}
    return {"plikow": len(wiersze), "bajtow": sum(w["rozmiar"] for w in wiersze), "potrzeba": potrzeba,
            "wolne": wolne, "starczy": wolne > potrzeba * 1.02 + 50_000_000, "cel": cel}


def wykonaj(db: sqlite3.Connection, postep=None, przerwij=None, usun_puste: bool = True) -> dict:
    przygotuj(db)
    spr = sprawdz(db)
    if spr.get("blad"):
        raise OSError(spr["blad"])
    if not spr["starczy"]:
        raise OSError(f"Za mało miejsca w miejscu docelowym: potrzeba {spr['potrzeba'] / 1e9:.1f} GB, "
                      f"wolne {spr['wolne'] / 1e9:.1f} GB.")
    cel_root = spr["cel"]
    wiersze = do_zrobienia(db)
    partia = int(time.time() * 1000)
    bajty = [0]
    razem = spr["bajtow"]
    ok = bledy = 0
    przeniesione_foldery: set[str] = set()
    from .stabilnosc import Straznik
    straznik = Straznik([r[0] for r in db.execute("SELECT DISTINCT korzen FROM pliki")] + [cel_root], przerwij,
                        getattr(postep, "czeka", None))
    biezacy = {"i": 0, "plik": "", "t": 0.0}

    def zglos(wymus=False):
        teraz = time.monotonic()
        if postep and (wymus or teraz - biezacy["t"] > 0.5):
            biezacy["t"] = teraz
            postep("kopiowanie", biezacy["i"], len(wiersze), bajty[0], bajty_razem=razem, plik=biezacy["plik"])

    def licz(n):  # w trakcie kopiowania — pasek rusza się także przy jednym dużym filmie
        bajty[0] += n
        zglos()

    for i, w in enumerate(wiersze, 1):
        if przerwij is not None and przerwij.is_set():
            raise Przerwano(w["sciezka"])
        biezacy.update(i=i - 1, plik=w["sciezka"])
        zglos(wymus=True)
        przed = bajty[0]
        for proba in range(3):
            bajty[0] = przed  # ponowienie po przerwie w sieci liczy plik od nowa
            try:
                _wykonaj_plik(db, w, cel_root, partia, przerwij, licz, przeniesione_foldery)
                ok += 1
                break
            except Przerwano:
                db.commit()
                raise
            except OSError as e:
                dst = os.path.join(cel_root, *w["cel"].split("/"))
                if proba < 2 and straznik.utracono(w["sciezka"], dst):
                    continue  # dysk wrócił — ten sam plik jeszcze raz (gotowa kopia zostanie rozpoznana)
                db.execute("UPDATE plan SET wynik=? WHERE id=?", (f"blad: {e.strerror or e}"[:300], w["id"]))
                bledy += 1
                break
        db.commit()  # po każdym pliku: kopiowanie następnego może trwać minuty
    db.commit()
    usuniete_foldery = _usun_puste(przeniesione_foldery, db) if usun_puste else 0
    if postep:
        postep("gotowe", len(wiersze), len(wiersze), bajty[0], bajty_razem=razem)
    return {"zrobione": ok, "bledy": bledy, "bajty": bajty[0], "partia": partia,
            "usuniete_foldery": usuniete_foldery}


def _wykonaj_plik(db, w, cel_root: str, partia: int, przerwij, licz, przeniesione_foldery: set) -> None:
    """Jeden plik planu: kopia/przeniesienie + wpis w dzienniku. OSError = nie udało się."""
    dst = os.path.join(cel_root, *w["cel"].split("/"))
    zrodlowy = db.execute("SELECT * FROM pliki WHERE rowid=?", (w["plik_id"],)).fetchone() \
        if w["plik_id"] is not None else None
    st = os.stat(w["sciezka"])
    if st.st_size != w["rozmiar"]:
        raise OSError("plik zmienił się od skanu — przeskanuj ponownie")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tryb_logu = w["tryb"]
    if os.path.exists(dst) and os.path.getsize(dst) == w["rozmiar"] and \
            _hash(dst, przerwij) == _hash(w["sciezka"], przerwij, licz):
        # identyczny plik już jest w bibliotece — nie tworzymy kopii „ (2)”
        usuniete = 0
        if w["tryb"] == "przenies":
            os.remove(w["sciezka"])
            usuniete = 1
            przeniesione_foldery.add(os.path.dirname(w["sciezka"]))
            if w["plik_id"] is not None:
                db.execute("DELETE FROM pliki WHERE rowid=?", (w["plik_id"],))
        _do_biblioteki(db, zrodlowy, dst, cel_root)
        db.execute("INSERT INTO wykonanie(partia, plan_id, zrodlo, cel, tryb, usuniete, rozmiar, mtime, czas) "
                   "VALUES (?,?,?,?,?,?,?,?,?)",
                   (partia, w["id"], w["sciezka"], dst, "juz_byl", usuniete, w["rozmiar"], st.st_mtime,
                    time.time()))
        db.execute("UPDATE plan SET wynik='ok' WHERE id=?", (w["id"],))
        return
    dst = _wolna(dst)
    usuniete = 0
    if w["tryb"] == "przenies" and ten_sam_wolumin(w["sciezka"], os.path.dirname(dst)):
        try:
            os.rename(w["sciezka"], dst)
            usuniete = 1
            licz(w["rozmiar"])
        except OSError:
            usuniete = 0
    if not usuniete:
        kopiuj_z_weryfikacja(w["sciezka"], dst, przerwij, licz)
        if w["tryb"] == "przenies":
            os.remove(w["sciezka"])
            usuniete = 1
    if usuniete:
        przeniesione_foldery.add(os.path.dirname(w["sciezka"]))
        if w["plik_id"] is not None:
            db.execute("DELETE FROM pliki WHERE rowid=?", (w["plik_id"],))
    _do_biblioteki(db, zrodlowy, dst, cel_root)
    db.execute("INSERT INTO wykonanie(partia, plan_id, zrodlo, cel, tryb, usuniete, rozmiar, mtime, czas) "
               "VALUES (?,?,?,?,?,?,?,?,?)",
               (partia, w["id"], w["sciezka"], dst, tryb_logu, usuniete, w["rozmiar"], st.st_mtime, time.time()))
    db.execute("UPDATE plan SET wynik='ok' WHERE id=?", (w["id"],))


def _do_biblioteki(db, zrodlowy, dst: str, cel_root: str) -> None:
    """Plik w bibliotece od razu trafia do bazy (z datą, GPS i aparatem źródła) — przeglądarka biblioteki
    i kolejne propozycje widzą go bez ponownego skanowania."""
    if zrodlowy is None:
        return
    try:
        st = os.stat(dst)
    except OSError:
        return
    dane = dict(zrodlowy)
    dane.update(sciezka=dst, korzen=os.path.abspath(cel_root), wzgledna=os.path.relpath(dst, cel_root),
                rozmiar=st.st_size, mtime=st.st_mtime, skan=0)
    kol = list(dane)
    db.execute(f"INSERT OR REPLACE INTO pliki({','.join(kol)}) VALUES ({','.join('?' * len(kol))})",
               [dane[k] for k in kol])


def _usun_puste(foldery: set[str], db) -> int:
    """Usuwa foldery źródłowe, które po przeniesieniu zostały puste (lub mają tylko śmieci)."""
    zrodla = [r[0] for r in db.execute("SELECT DISTINCT korzen FROM pliki")]
    granice = {os.path.normcase(os.path.normpath(z)) for z in zrodla}
    usuniete = 0
    for f in sorted(foldery, key=len, reverse=True):
        while f and os.path.normcase(os.path.normpath(f)) not in granice:
            try:
                wpisy = list(os.scandir(f))
            except OSError:
                break
            if any(not (typy.pominac_plik(w.name) if w.is_file() else typy.pominac_folder(w.name)) for w in wpisy):
                break
            try:
                for w in wpisy:
                    shutil.rmtree(w.path) if w.is_dir() else os.remove(w.path)
                os.rmdir(f)
                usuniete += 1
            except OSError:
                break
            nf = os.path.dirname(f)
            if nf == f:
                break
            f = nf
    return usuniete


def ostatnia_partia(db: sqlite3.Connection) -> dict | None:
    przygotuj(db)
    r = db.execute("SELECT partia, COUNT(*) n, SUM(usuniete) przeniesione FROM wykonanie WHERE cofniete=0 "
                   "GROUP BY partia ORDER BY partia DESC LIMIT 1").fetchone()
    return dict(r) if r else None


def cofnij(db: sqlite3.Connection, postep=None, przerwij=None) -> dict:
    """Cofa ostatnie porządkowanie: kopie są usuwane, przeniesione pliki wracają na miejsce."""
    ost = ostatnia_partia(db)
    if not ost:
        return {"cofniete": 0, "bledy": []}
    wiersze = db.execute("SELECT * FROM wykonanie WHERE partia=? AND cofniete=0 ORDER BY id DESC",
                         (ost["partia"],)).fetchall()
    cofniete, bledy = 0, []
    foldery_celu: set[str] = set()
    from .skaner import Zatwierdzanie
    zatwierdz = Zatwierdzanie(db)  # krótkie transakcje — cofanie 50 tys. plików trwa
    for i, w in enumerate(wiersze, 1):
        if przerwij is not None and przerwij.is_set():
            db.commit()
            raise Przerwano(w["cel"])
        if postep and (i % 20 == 1 or i == len(wiersze)):
            postep("cofanie", i - 1, len(wiersze), 0, plik=w["cel"])
        try:
            if not os.path.exists(w["cel"]):
                raise OSError(f"nie ma już pliku {w['cel']}")
            if os.path.getsize(w["cel"]) != w["rozmiar"]:
                raise OSError(f"plik zmieniony po uporządkowaniu: {w['cel']}")
            if w["tryb"] == "juz_byl":
                # plik był w bibliotece wcześniej — zostaje; przywracamy tylko usunięty oryginał
                if w["usuniete"] and not os.path.exists(w["zrodlo"]):
                    os.makedirs(os.path.dirname(w["zrodlo"]), exist_ok=True)
                    kopiuj_z_weryfikacja(w["cel"], w["zrodlo"], przerwij)
            elif w["usuniete"]:
                if os.path.exists(w["zrodlo"]):
                    raise OSError(f"w miejscu oryginału jest już plik: {w['zrodlo']}")
                os.makedirs(os.path.dirname(w["zrodlo"]), exist_ok=True)
                if ten_sam_wolumin(w["cel"], os.path.dirname(w["zrodlo"])):
                    os.rename(w["cel"], w["zrodlo"])
                else:
                    kopiuj_z_weryfikacja(w["cel"], w["zrodlo"], przerwij)
                    os.remove(w["cel"])
            else:
                os.remove(w["cel"])
            if w["tryb"] != "juz_byl":
                foldery_celu.add(os.path.dirname(w["cel"]))
            db.execute("UPDATE wykonanie SET cofniete=1 WHERE id=?", (w["id"],))
            if w["tryb"] != "juz_byl":
                db.execute("DELETE FROM pliki WHERE sciezka=?", (w["cel"],))  # nie ma go już w bibliotece
            db.execute("UPDATE plan SET wynik=NULL WHERE id=?", (w["plan_id"],))
            cofniete += 1
        except OSError as e:
            bledy.append(str(e))
        zatwierdz()
    db.commit()
    granica = os.path.normcase(os.path.normpath(planista.meta(db).get("cel", "")))
    for f in sorted(foldery_celu, key=len, reverse=True):
        while f and os.path.normcase(os.path.normpath(f)) != granica and granica:
            try:
                os.rmdir(f)  # tylko puste
            except OSError:
                break
            f = os.path.dirname(f)
    return {"cofniete": cofniete, "bledy": bledy}
