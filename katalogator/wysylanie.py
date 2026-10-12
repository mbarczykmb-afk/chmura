"""📤 Zdjęcia i filmy wysłane z telefonu (albo z innego komputera) prosto do biblioteki.

Plik trafia do `<biblioteka>/Z telefonu/<RRRR-MM>/` (miesiąc zrobienia zdjęcia — z EXIF-u, a gdy go brak, z daty
pliku w telefonie). Ten sam plik wysłany drugi raz (identyczna zawartość) nie tworzy kopii.
"""

from __future__ import annotations

import hashlib
import os
import re
import time

from . import metadane, skaner, typy

FOLDER = "Z telefonu"
MAKS = 50 * 1024 ** 3  # 50 GB — jeden film


def _bezpieczna(nazwa: str) -> str:
    nazwa = os.path.basename(str(nazwa or "").replace("\\", "/"))
    nazwa = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", nazwa).strip(" .")
    return nazwa[:180] or "plik"


def _sha(sciezka: str) -> str:
    h = hashlib.sha1()
    with open(sciezka, "rb") as f:
        for k in iter(lambda: f.read(1 << 20), b""):
            h.update(k)
    return h.hexdigest()


def przyjmij(baza, cel: str, nazwa: str, mtime: float | None, strumien, dlugosc: int) -> dict:
    """Zapisuje `dlugosc` bajtów ze `strumien` do biblioteki `cel` i dopisuje plik do bazy projektu."""
    if not cel or not os.path.isdir(cel):
        return {"blad": "Najpierw wybierz na komputerze miejsce docelowe (bibliotekę) — tam trafiają wysłane zdjęcia."}
    nazwa = _bezpieczna(nazwa)
    rodz = typy.rodzaj(nazwa)
    if rodz not in (typy.ZDJECIE, typy.FILM):
        return {"blad": f"„{nazwa}” to nie zdjęcie ani film."}
    if not 0 < dlugosc <= MAKS:
        return {"blad": "Pusty albo zbyt duży plik."}
    katalog = os.path.join(cel, FOLDER)
    os.makedirs(katalog, exist_ok=True)
    tymcz = os.path.join(katalog, f".{nazwa}.{os.getpid()}.{time.time_ns()}.part")
    h = hashlib.sha1()
    try:
        with open(tymcz, "wb") as f:
            zostalo = dlugosc
            while zostalo > 0:
                k = strumien.read(min(1 << 20, zostalo))
                if not k:
                    raise ConnectionError("przerwane wysyłanie")
                f.write(k)
                h.update(k)
                zostalo -= len(k)
        if mtime:
            os.utime(tymcz, (mtime, mtime))
        sha = h.hexdigest()
        db = skaner.otworz_baze(baza)
        try:
            # już jest w bibliotece? (ten sam rozmiar → porównanie zawartości)
            pref = os.path.abspath(cel).rstrip("\\/") + os.sep
            for (sc,) in db.execute("SELECT sciezka FROM pliki WHERE rozmiar=? AND substr(sciezka, 1, ?)=?",
                                    (dlugosc, len(pref), pref)).fetchall():
                try:
                    if os.path.isfile(sc) and _sha(sc) == sha:
                        os.remove(tymcz)
                        return {"ok": True, "juz_jest": True, "nazwa": os.path.basename(sc),
                                "folder": os.path.relpath(os.path.dirname(sc), cel)}
                except OSError:
                    continue
            m = metadane.odczytaj(tymcz, rodz, mtime or time.time())
            kiedy = m.data or time.localtime(mtime or time.time())
            miesiac = kiedy.strftime("%Y-%m") if hasattr(kiedy, "strftime") else time.strftime("%Y-%m", kiedy)
            folder = os.path.join(katalog, miesiac)
            os.makedirs(folder, exist_ok=True)
            rdzen, rozsz = os.path.splitext(nazwa)
            docel = os.path.join(folder, nazwa)
            i = 2
            while os.path.exists(docel):
                docel = os.path.join(folder, f"{rdzen} ({i}){rozsz}")
                i += 1
            os.replace(tymcz, docel)
            rowid = skaner.dodaj_plik(db, docel, cel)
        finally:
            db.close()
    except BaseException:
        try:
            os.remove(tymcz)
        except OSError:
            pass
        raise
    return {"ok": True, "id": rowid, "nazwa": os.path.basename(docel), "folder": os.path.relpath(folder, cel)}
