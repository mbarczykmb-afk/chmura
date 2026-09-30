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
    for r in db.execute("SELECT rowid id, sciezka, wzgledna, korzen, rozmiar, rodzaj, aparat, lat, zrodlo_daty "
                        "FROM pliki ORDER BY sciezka"):
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
    for k in korzenie:
        try:
            os.rmdir(os.path.join(k, duplikaty.FOLDER_ODLOZONE))  # tylko gdy pusty
        except OSError:
            pass
    db.commit()
    if postep:
        postep("gotowe", usuniete, wszystkie, bajty)
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

