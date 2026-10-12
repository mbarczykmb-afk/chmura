"""💾 Kopia zapasowa biblioteki i sprawdzanie, czy pliki nie uległy uszkodzeniu.

Kopia: lustro biblioteki w drugim miejscu (inny dysk, NAS) — kopiowane są tylko nowe i zmienione pliki, a z kopii
nic nie jest usuwane (zdjęcie skasowane przez pomyłkę w bibliotece zostaje w kopii). Folder „Odłożone” (kosz
programu) nie jest kopiowany.

Sprawdzanie: suma SHA-1 każdego pliku zapisana przy pierwszym czytaniu. Gdy później zawartość jest inna, a rozmiar
i data pliku te same — plik uległ uszkodzeniu (np. dysk), a nie edycji. Wtedy można przywrócić go z kopii (jeśli
kopia ma właściwą sumę). Sprawdzanie można przerwać — następnym razem zaczyna od plików jeszcze niesprawdzonych.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import time
from pathlib import Path

from . import typy
from .duplikaty import FOLDER_ODLOZONE

SCHEMAT = """
CREATE TABLE IF NOT EXISTS sumy (sciezka TEXT PRIMARY KEY, rozmiar INTEGER NOT NULL, mtime REAL NOT NULL,
                                 sha TEXT NOT NULL, sprawdzone REAL NOT NULL);
CREATE TABLE IF NOT EXISTS problemy (sciezka TEXT PRIMARY KEY, rodzaj TEXT NOT NULL, opis TEXT NOT NULL,
                                     z_kopii INTEGER NOT NULL DEFAULT 0, czas REAL NOT NULL);
"""
CO_DNI = 30          # ten sam plik sprawdzamy ponownie najwcześniej po miesiącu
TMP = ".katalogator-tmp"
OTWIERANE = {".jpg", ".jpeg", ".png"}  # tylko tu PIL umie sprawdzić cały plik


class Przerwano(Exception):
    pass


def baza(katalog: Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(Path(katalog) / "kopia.db"), timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMAT)
    return db


def _pliki(korzen: str):
    """(ścieżka, stat) wszystkich plików biblioteki — bez kosza programu i plików systemowych."""
    stos = [korzen]
    while stos:
        folder = stos.pop()
        try:
            wpisy = sorted(os.scandir(folder), key=lambda w: w.name)
        except OSError:
            continue
        for w in wpisy:
            try:
                if w.is_dir(follow_symlinks=False):
                    if not typy.pominac_folder(w.name) and not (folder == korzen and w.name == FOLDER_ODLOZONE):
                        stos.append(w.path)
                elif w.is_file(follow_symlinks=False) and not typy.pominac_plik(w.name):
                    yield w.path, w.stat(follow_symlinks=False)
            except OSError:
                continue


def _w_srodku(a: str, b: str) -> bool:
    a, b = os.path.normcase(os.path.abspath(a)), os.path.normcase(os.path.abspath(b))
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def sprawdz_miejsce(zrodlo: str, cel: str) -> str | None:
    if not zrodlo or not os.path.isdir(zrodlo):
        return "Najpierw wybierz bibliotekę (miejsce docelowe porządkowania)."
    if not cel:
        return "Wybierz folder na kopię — najlepiej na innym dysku albo NAS-ie."
    if _w_srodku(cel, zrodlo) or _w_srodku(zrodlo, cel):
        return "Kopia nie może być w bibliotece (ani biblioteka w kopii) — wybierz inny dysk."
    return None


def _kopiuj_plik(z: str, do: str, postep_bajty) -> None:
    os.makedirs(os.path.dirname(do), exist_ok=True)
    tmp = do + TMP
    with open(z, "rb") as fz, open(tmp, "wb") as fd:
        while True:
            k = fz.read(4 << 20)
            if not k:
                break
            fd.write(k)
            postep_bajty(len(k))
    shutil.copystat(z, tmp)
    os.replace(tmp, do)


def kopiuj(zrodlo: str, cel: str, postep=None, przerwij=None) -> dict:
    """Nowe i zmienione pliki biblioteki → kopia. Z kopii nic nie znika."""
    blad = sprawdz_miejsce(zrodlo, cel)
    if blad:
        raise ValueError(blad)
    os.makedirs(cel, exist_ok=True)
    do_zrobienia, bez_zmian = [], 0
    for sc, st in _pliki(zrodlo):
        if przerwij is not None and przerwij.is_set():
            raise Przerwano()
        do = os.path.join(cel, os.path.relpath(sc, zrodlo))
        try:
            sd = os.stat(do)
            if sd.st_size == st.st_size and abs(sd.st_mtime - st.st_mtime) < 2:
                bez_zmian += 1
                continue
        except OSError:
            pass
        do_zrobienia.append((sc, do, st.st_size))
        if postep and len(do_zrobienia) % 200 == 0:
            postep("porównywanie", len(do_zrobienia) + bez_zmian, 0, 0)
    razem = sum(r for _, _, r in do_zrobienia)
    bajty, skopiowane, bledy = 0, 0, []

    def dodaj(n):
        nonlocal bajty
        bajty += n
        if przerwij is not None and przerwij.is_set():
            raise Przerwano()

    for i, (sc, do, _) in enumerate(do_zrobienia):
        if postep:
            postep("kopiowanie", i, len(do_zrobienia), bajty, bajty_razem=razem, plik=os.path.relpath(sc, zrodlo))
        try:
            _kopiuj_plik(sc, do, dodaj)
            skopiowane += 1
        except Przerwano:
            try:
                os.remove(do + TMP)
            except OSError:
                pass
            raise
        except OSError as e:
            bledy.append(f"{os.path.relpath(sc, zrodlo)}: {e.strerror or e}")
    return {"skopiowane": skopiowane, "bajty": bajty, "bez_zmian": bez_zmian, "bledy": bledy[:50],
            "liczba_bledow": len(bledy), "czas": time.time()}


def _sha(sciezka: str, dodaj=None) -> str:
    h = hashlib.sha1()
    with open(sciezka, "rb") as f:
        while True:
            k = f.read(4 << 20)
            if not k:
                break
            h.update(k)
            if dodaj:
                dodaj(len(k))
    return h.hexdigest()


def _otwiera_sie(sciezka: str) -> bool:
    if os.path.splitext(sciezka)[1].lower() not in OTWIERANE:
        return True
    try:
        from PIL import Image
        with Image.open(sciezka) as im:
            im.verify()
        return True
    except Exception:
        return False


def _problem(db, sc: str, rodzaj: str, opis: str, z_kopii: bool = False) -> None:
    db.execute("INSERT OR REPLACE INTO problemy VALUES (?,?,?,?,?)", (sc, rodzaj, opis, int(z_kopii), time.time()))


def sprawdz(db: sqlite3.Connection, zrodlo: str, kopia_folder: str | None = None, postep=None, przerwij=None,
            co_dni: float = CO_DNI) -> dict:
    """Sprawdza pliki biblioteki (i ich odpowiedniki w kopii) z zapisanymi sumami. Wznawialne."""
    if not zrodlo or not os.path.isdir(zrodlo):
        raise ValueError("Najpierw wybierz bibliotekę (miejsce docelowe porządkowania).")
    kopia_folder = kopia_folder if kopia_folder and os.path.isdir(kopia_folder) else None
    teraz = time.time()
    znane = {r["sciezka"]: r for r in db.execute("SELECT * FROM sumy")}
    kolejka, pominiete = [], 0
    for sc, st in _pliki(zrodlo):
        r = znane.get(sc)
        if r and r["rozmiar"] == st.st_size and abs(r["mtime"] - st.st_mtime) < 2 and teraz - r["sprawdzone"] < co_dni * 86400:
            pominiete += 1
            continue
        kolejka.append((sc, st, r))
    kolejka.sort(key=lambda x: x[2]["sprawdzone"] if x[2] else 0)  # najpierw nowe i najdawniej sprawdzane
    razem = sum(st.st_size for _, st, _ in kolejka)
    bajty, nowe, dobre, zle, ostatni_zapis = 0, 0, 0, 0, time.monotonic()

    def dodaj(n):
        nonlocal bajty
        bajty += n
        if przerwij is not None and przerwij.is_set():
            raise Przerwano()

    try:
        for i, (sc, st, r) in enumerate(kolejka):
            if postep:
                postep("sprawdzanie", i, len(kolejka), bajty, bajty_razem=razem, plik=os.path.relpath(sc, zrodlo))
            kop = os.path.join(kopia_folder, os.path.relpath(sc, zrodlo)) if kopia_folder else None
            try:
                sha = _sha(sc, dodaj)
            except OSError as e:
                _problem(db, sc, "odczyt", f"Nie da się odczytać: {e.strerror or e}")
                zle += 1
                continue
            if r and r["rozmiar"] == st.st_size and abs(r["mtime"] - st.st_mtime) < 2 and r["sha"] != sha:
                # ta sama data i rozmiar, inna zawartość — uszkodzenie, nie edycja
                z_kopii = bool(kop and os.path.isfile(kop) and _sha(kop) == r["sha"])
                _problem(db, sc, "uszkodzony", "Zawartość zmieniła się, choć data i rozmiar pliku są te same — "
                         "prawdopodobnie uszkodzenie dysku." + (" W kopii jest dobra wersja." if z_kopii else ""), z_kopii)
                zle += 1
                continue
            if not r or r["rozmiar"] != st.st_size or abs(r["mtime"] - st.st_mtime) >= 2:
                nowe += 1
                if not _otwiera_sie(sc):
                    _problem(db, sc, "nie_otwiera", "Zdjęcia nie da się otworzyć — plik jest niekompletny albo uszkodzony.")
                    zle += 1
                    continue
            if kop and os.path.isfile(kop) and os.path.getsize(kop) == st.st_size and _sha(kop, dodaj) != sha:
                _problem(db, sc, "kopia", "Plik w kopii ma inną zawartość niż w bibliotece (uszkodzona kopia) — "
                         "„Napraw kopię” skopiuje go jeszcze raz.")
                zle += 1
            else:
                db.execute("DELETE FROM problemy WHERE sciezka=?", (sc,))
                dobre += 1
            db.execute("INSERT OR REPLACE INTO sumy VALUES (?,?,?,?,?)", (sc, st.st_size, st.st_mtime, sha, time.time()))
            if time.monotonic() - ostatni_zapis > 2:
                db.commit()
                ostatni_zapis = time.monotonic()
    finally:
        db.commit()
    return {"sprawdzone": dobre + zle, "nowe": nowe, "dobre": dobre, "problemy": zle, "pominiete": pominiete,
            "bajty": bajty, "czas": time.time(), "wszystkich_problemow": db.execute("SELECT COUNT(*) FROM problemy").fetchone()[0]}


def problemy(db: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in db.execute("SELECT * FROM problemy ORDER BY czas DESC LIMIT 500")]


def zapomnij(db: sqlite3.Connection, sciezki) -> None:
    """Plik zmieniony przez program (data, miejsce w EXIF-ie bez zmiany daty pliku) — to nie uszkodzenie."""
    for sc in sciezki or ():
        db.execute("DELETE FROM sumy WHERE sciezka=?", (sc,))
        db.execute("DELETE FROM problemy WHERE sciezka=?", (sc,))
    db.commit()


def przyjmij(db: sqlite3.Connection, sciezka: str) -> dict:
    """„To moja zmiana” — obecna zawartość jest dobra."""
    zapomnij(db, [sciezka])
    return {"ok": True}


def przywroc(db: sqlite3.Connection, zrodlo: str, kopia_folder: str, sciezka: str) -> dict:
    """Zastępuje uszkodzony plik dobrą wersją z kopii; uszkodzony trafia do Odłożone/Uszkodzone."""
    r = db.execute("SELECT * FROM sumy WHERE sciezka=?", (sciezka,)).fetchone()
    if not r or not kopia_folder or not _w_srodku(sciezka, zrodlo):
        return {"blad": "Nie ma czego przywrócić."}
    kop = os.path.join(kopia_folder, os.path.relpath(sciezka, zrodlo))
    if not os.path.isfile(kop) or _sha(kop) != r["sha"]:
        return {"blad": "W kopii nie ma dobrej wersji tego pliku."}
    odl = os.path.join(zrodlo, FOLDER_ODLOZONE, "Uszkodzone", os.path.relpath(sciezka, zrodlo))
    os.makedirs(os.path.dirname(odl), exist_ok=True)
    if os.path.exists(sciezka):
        if os.path.exists(odl):
            os.remove(sciezka)
        else:
            os.replace(sciezka, odl)
    _kopiuj_plik(kop, sciezka, lambda n: None)
    st = os.stat(sciezka)
    db.execute("UPDATE sumy SET rozmiar=?, mtime=?, sprawdzone=? WHERE sciezka=?", (st.st_size, st.st_mtime, time.time(), sciezka))
    db.execute("DELETE FROM problemy WHERE sciezka=?", (sciezka,))
    db.commit()
    return {"ok": True, "odlozony": odl}


def napraw_kopie(db: sqlite3.Connection, zrodlo: str, kopia_folder: str, sciezka: str) -> dict:
    """Uszkodzony plik w kopii — kopiujemy go jeszcze raz z biblioteki (o ile biblioteka ma zapisaną sumę)."""
    r = db.execute("SELECT sha FROM sumy WHERE sciezka=?", (sciezka,)).fetchone()
    if not kopia_folder or not _w_srodku(sciezka, zrodlo) or not os.path.isfile(sciezka):
        return {"blad": "Nie ma czego naprawić."}
    if r and _sha(sciezka) != r["sha"]:
        return {"blad": "Plik w bibliotece też się zmienił — sprawdź go najpierw."}
    _kopiuj_plik(sciezka, os.path.join(kopia_folder, os.path.relpath(sciezka, zrodlo)), lambda n: None)
    db.execute("DELETE FROM problemy WHERE sciezka=?", (sciezka,))
    db.commit()
    return {"ok": True}
