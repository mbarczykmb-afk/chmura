"""Sprzątanie dysku na miejscu: duplikaty, śmieci, podobne i nieostre zdjęcia są odkładane do
`<folder>/Odłożone/…` (można cofnąć), a stamtąd — na wyraźne życzenie — usuwane na stałe.
Bez kopiowania, przenoszenia do biblioteki i bez drzewa."""

from __future__ import annotations

import os
import sqlite3

from . import duplikaty, kategorie
from .skaner import Przerwano


def lista_smieci(db: sqlite3.Connection) -> list[dict]:
    """Śmieci w wybranych folderach (puste pliki, pliki tymczasowe, skróty, ikony, miniatury) z powodem."""
    kategorie.przygotuj(db)
    wym = kategorie.wymiary(db)
    dec = kategorie.decyzje(db)
    wynik = []
    # wstępny filtr w SQL (nadzbiór — dokładnie sprawdza kategorie.smieci): przy 300 tys. plików nie budujemy
    # słownika dla każdego zdjęcia z aparatu
    rozsz = " OR ".join(f"p.sciezka LIKE '%{e}'" for e in sorted(kategorie._EXT_SMIECI))
    slowa = " OR ".join(f"COALESCE(p.wzgledna, p.sciezka) LIKE '%{w}%'" for w in ("thumb", "cache", "temp", "tmp", "sticker"))
    for r in db.execute(f"""SELECT p.rowid id, p.sciezka, p.wzgledna, p.korzen, p.rozmiar, p.rodzaj, p.aparat, p.lat,
                                   p.zrodlo_daty FROM pliki p LEFT JOIN kategorie k ON k.sciezka = p.sciezka
                            WHERE p.rozmiar = 0 OR k.kategoria = 'smieci' OR {rozsz} OR {slowa}
                               OR (p.rodzaj = 'zdjecie' AND p.aparat IS NULL AND p.lat IS NULL
                                   AND COALESCE(p.zrodlo_daty, '') <> 'exif')
                            ORDER BY p.sciezka"""):
        p = dict(r)
        if dec.get(p["sciezka"]) in ("zdjecie", "dokument"):
            continue  # użytkownik uznał, że to nie śmieć
        powod = "Twoja decyzja: śmieci" if dec.get(p["sciezka"]) == "smieci" else kategorie.smieci(p, wym.get(p["sciezka"]))
        if powod:
            p["powod"] = powod
            wynik.append(p)
    return wynik


def _odlozone_foldery(korzenie: list[str]) -> list[tuple[str, str]]:
    """[(ścieżka folderu Odłożone/<kategoria>, kategoria)] dla wybranych folderów."""
    wynik = []
    for k in korzenie:
        baza = os.path.join(k, duplikaty.FOLDER_ODLOZONE)
        if not os.path.isdir(baza):
            continue
        try:
            for w in os.scandir(baza):
                if w.is_dir(follow_symlinks=False):
                    wynik.append((w.path, w.name))
        except OSError:
            continue
    return wynik


def odlozone(korzenie: list[str]) -> dict:
    """Ile plików i bajtów czeka w folderach Odłożone (po kategoriach)."""
    kat: dict[str, dict] = {}
    for sciezka, nazwa in _odlozone_foldery(korzenie):
        d = kat.setdefault(nazwa, {"nazwa": nazwa, "plikow": 0, "bajty": 0, "foldery": []})
        d["foldery"].append(sciezka)
        for gdzie, _, pliki in os.walk(sciezka):
            for n in pliki:
                try:
                    d["bajty"] += os.path.getsize(os.path.join(gdzie, n))
                    d["plikow"] += 1
                except OSError:
                    continue
    lista = sorted(kat.values(), key=lambda d: -d["bajty"])
    return {"kategorie": lista, "plikow": sum(d["plikow"] for d in lista), "bajty": sum(d["bajty"] for d in lista)}


def usun_odlozone(db: sqlite3.Connection, korzenie: list[str], kategorie_: list[str] | None = None,
                  postep=None, przerwij=None) -> dict:
    """Usuwa NA STAŁE pliki z <folder>/Odłożone/<kategoria> (tylko tam — nigdzie indziej)."""
    duplikaty.przygotuj(db)
    cele = [(s, n) for s, n in _odlozone_foldery(korzenie) if kategorie_ is None or n in kategorie_]
    wszystkie = sum(len(p) for s, _ in cele for _, _, p in os.walk(s))
    usuniete, bajty, bledy = 0, 0, []
    for sciezka, _ in cele:
        # bezpiecznik: tylko folder bezpośrednio w <korzeń>/Odłożone
        if os.path.basename(os.path.dirname(sciezka)) != duplikaty.FOLDER_ODLOZONE:
            continue
        for gdzie, _, pliki in os.walk(sciezka, topdown=False):
            for n in pliki:
                if przerwij is not None and przerwij.is_set():
                    raise Przerwano(gdzie)
                p = os.path.join(gdzie, n)
                try:
                    r = os.path.getsize(p)
                    os.remove(p)
                    usuniete += 1
                    bajty += r
                except OSError as e:
                    bledy.append(f"{p}: {e.strerror or e}")
                if postep and usuniete % 50 == 0:
                    postep("usuwanie", usuniete, wszystkie, bajty)
            try:
                os.rmdir(gdzie)
            except OSError:
                pass
        # tych plików nie da się już przywrócić — „Cofnij” w Duplikatach ich nie obiecuje
        db.execute("DELETE FROM operacje WHERE substr(do_, 1, ?) = ?", (len(sciezka) + 1, sciezka + os.sep))
        db.commit()
    for k in korzenie:
        try:
            os.rmdir(os.path.join(k, duplikaty.FOLDER_ODLOZONE))  # tylko gdy pusty
        except OSError:
            pass
    db.commit()
    if postep:
        postep("gotowe", usuniete, wszystkie, bajty)
    return {"usuniete": usuniete, "bajty": bajty, "bledy": bledy[:50]}


def usun_partie(db: sqlite3.Connection, partia: int, postep=None, przerwij=None) -> dict:
    """Usuwa NA STAŁE tylko pliki odłożone w jednej operacji (np. „od razu usuń na stałe” w Duplikatach)."""
    duplikaty.przygotuj(db)
    ops = db.execute("SELECT id, do_ FROM operacje WHERE partia=? AND cofnieta=0", (int(partia),)).fetchall()
    usuniete, bajty, bledy, foldery = 0, 0, [], set()
    for i, op in enumerate(ops, 1):
        if przerwij is not None and przerwij.is_set():
            raise Przerwano(op["do_"])
        p = op["do_"]
        if duplikaty.FOLDER_ODLOZONE not in p.replace("\\", "/").split("/"):
            continue  # bezpiecznik: kasujemy wyłącznie w folderach Odłożone
        try:
            r = os.path.getsize(p)
            os.remove(p)
            usuniete += 1
            bajty += r
        except FileNotFoundError:
            pass
        except OSError as e:
            bledy.append(f"{p}: {e.strerror or e}")
            continue
        foldery.add(os.path.dirname(p))
        db.execute("DELETE FROM operacje WHERE id=?", (op["id"],))
        db.commit()  # bez długiej blokady bazy w trakcie kasowania po sieci
        if postep and i % 50 == 0:
            postep("usuwanie", i, len(ops), bajty)
    db.commit()
    for f in sorted(foldery, key=len, reverse=True):  # puste podfoldery w Odłożone — aż do samego „Odłożone”
        while duplikaty.FOLDER_ODLOZONE in f.replace("\\", "/").split("/"):
            try:
                os.rmdir(f)
            except OSError:
                break
            if os.path.basename(f) == duplikaty.FOLDER_ODLOZONE:
                break
            f = os.path.dirname(f)
    if postep:
        postep("gotowe", usuniete, len(ops), bajty)
    return {"usuniete": usuniete, "bajty": bajty, "bledy": bledy[:50]}


def usun_puste_foldery(korzenie: list[str]) -> int:
    """Puste foldery (albo z samymi śmieciami systemu: Thumbs.db, desktop.ini, .DS_Store…) w wybranych
    folderach — same wybrane foldery i „Odłożone” zostają."""
    from .wykonawca import _usun_puste
    foldery = set()
    for k in korzenie:
        for gdzie, podf, _ in os.walk(k):
            podf[:] = [d for d in podf if d != duplikaty.FOLDER_ODLOZONE and not d.startswith(".")]
            foldery.add(gdzie)
    return _usun_puste(foldery, korzenie)

