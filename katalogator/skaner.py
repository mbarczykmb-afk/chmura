"""Skanowanie folderów do lokalnej bazy SQLite (wznawialne)."""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import typy
from .metadane import odczytaj

SCHEMAT = """
CREATE TABLE IF NOT EXISTS pliki (
    sciezka     TEXT PRIMARY KEY,
    korzen      TEXT NOT NULL,
    wzgledna    TEXT NOT NULL,
    rozmiar     INTEGER NOT NULL,
    mtime       REAL NOT NULL,
    rodzaj      TEXT NOT NULL,
    rozszerzenie TEXT NOT NULL,
    data        TEXT,
    zrodlo_daty TEXT,
    lat         REAL,
    lon         REAL,
    aparat      TEXT,
    wykonawca   TEXT,
    album       TEXT,
    tytul       TEXT,
    blad        TEXT,
    skan        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_pliki_korzen ON pliki(korzen);
CREATE TABLE IF NOT EXISTS skany (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    korzen    TEXT NOT NULL,
    start     REAL NOT NULL,
    koniec    REAL,
    pominiete_pliki   INTEGER DEFAULT 0,
    pominiete_foldery INTEGER DEFAULT 0,
    bledy_dostepu     INTEGER DEFAULT 0
);
"""


def otworz_baze(sciezka: str | Path) -> sqlite3.Connection:
    """Połączenie z bazą projektu. Tryb WAL: odczyt (np. odświeżanie okna) nigdy nie czeka na zapis
    zadania w tle, a zapis czeka do 30 s na zakończenie cudzej transakcji zamiast od razu zgłaszać
    „database is locked”."""
    db = sqlite3.connect(str(sciezka), timeout=30)
    db.row_factory = sqlite3.Row
    if str(sciezka) != ":memory:":
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA busy_timeout=30000")
    db.executescript(SCHEMAT)
    return db


class Zatwierdzanie:
    """Zatwierdza transakcję najwyżej co `co` sekund — zadania w tle nie trzymają blokady zapisu długo."""

    def __init__(self, db: sqlite3.Connection, co: float = 1.0):
        self.db, self.co, self.ostatnio = db, co, time.monotonic()

    def __call__(self, wymus: bool = False) -> None:
        if wymus or time.monotonic() - self.ostatnio >= self.co:
            self.db.commit()
            self.ostatnio = time.monotonic()


def _przejdz(korzen: str, licz: dict):
    """Rekurencyjnie zwraca (ścieżka, nazwa, stat) z pominięciem śmieci."""
    stos = [korzen]
    while stos:
        folder = stos.pop()
        try:
            wpisy = list(os.scandir(folder))
        except OSError:
            licz["bledy_dostepu"] += 1
            continue
        for w in wpisy:
            try:
                if w.is_dir(follow_symlinks=False):
                    if typy.pominac_folder(w.name):
                        licz["pominiete_foldery"] += 1
                    else:
                        stos.append(w.path)
                elif w.is_file(follow_symlinks=False):
                    if typy.pominac_plik(w.name):
                        licz["pominiete_pliki"] += 1
                    else:
                        yield w.path, w.name, w.stat(follow_symlinks=False)
            except OSError:
                licz["bledy_dostepu"] += 1


class Przerwano(Exception):
    """Skan przerwany na życzenie — postęp jest zapisany w bazie."""


def skanuj(korzen: str, db: sqlite3.Connection, watki: int = 8, wypisz=print,
           postep=None, przerwij=None) -> dict:
    """postep(liczba_plikow, folder) — wywoływane co ok. 0,5 s; przerwij — threading.Event."""
    korzen = os.path.abspath(korzen)
    if not os.path.isdir(korzen):
        raise NotADirectoryError(korzen)
    cur = db.execute("INSERT INTO skany(korzen, start) VALUES (?, ?)", (korzen, time.time()))
    skan_id = cur.lastrowid
    db.commit()  # nie trzymaj blokady zapisu podczas przeglądania folderów
    znane = {
        r["sciezka"]: (r["rozmiar"], r["mtime"])
        for r in db.execute("SELECT sciezka, rozmiar, mtime FROM pliki WHERE korzen = ?", (korzen,))
    }
    licz = {"pominiete_pliki": 0, "pominiete_foldery": 0, "bledy_dostepu": 0}
    stat = {"wszystkie": 0, "nowe_lub_zmienione": 0, "bez_zmian": 0}
    niezmienione: list[str] = []
    ostatni_wydruk = time.time()

    def zadanie(el):
        sciezka, nazwa, st = el
        rodz = typy.rodzaj(nazwa)
        return sciezka, st, rodz, odczytaj(sciezka, rodz, st.st_mtime)

    def zapisz(wynik):
        sciezka, st, rodz, m = wynik
        db.execute(
            "INSERT OR REPLACE INTO pliki VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sciezka, korzen, os.path.relpath(sciezka, korzen), st.st_size, st.st_mtime,
                rodz, Path(sciezka).suffix.lower(),
                m.data.isoformat(timespec="seconds") if m.data else None, m.zrodlo_daty,
                m.lat, m.lon, m.aparat, m.wykonawca, m.album, m.tytul, m.blad, skan_id,
            ),
        )

    with ThreadPoolExecutor(max_workers=watki) as pula:
        oczekujace = []
        for el in _przejdz(korzen, licz):
            stat["wszystkie"] += 1
            sciezka, _, st = el
            if znane.get(sciezka) == (st.st_size, st.st_mtime):
                stat["bez_zmian"] += 1
                niezmienione.append(sciezka)
            else:
                stat["nowe_lub_zmienione"] += 1
                oczekujace.append(pula.submit(zadanie, el))
            if len(oczekujace) >= 64:
                for f in oczekujace:
                    zapisz(f.result())
                oczekujace.clear()
                db.commit()
            if przerwij is not None and przerwij.is_set():
                for f in oczekujace:
                    zapisz(f.result())
                db.commit()
                raise Przerwano(korzen)
            teraz = time.time()
            if postep is not None and teraz - ostatni_wydruk > 0.5:
                postep(stat["wszystkie"], os.path.dirname(sciezka))
                ostatni_wydruk = teraz
            elif postep is None and teraz - ostatni_wydruk > 2:
                wypisz(f"  ...przejrzano {stat['wszystkie']} plików")
                ostatni_wydruk = teraz
        for f in oczekujace:
            zapisz(f.result())
    if postep is not None:
        postep(stat["wszystkie"], korzen)

    # Oznacz pliki bez zmian jako widziane w tym skanie, usuń te, których już nie ma.
    for i in range(0, len(niezmienione), 500):
        paczka = niezmienione[i:i + 500]
        db.execute(
            f"UPDATE pliki SET skan = ? WHERE sciezka IN ({','.join('?' * len(paczka))})",
            [skan_id, *paczka],
        )
    usuniete = db.execute(
        "DELETE FROM pliki WHERE korzen = ? AND skan != ?", (korzen, skan_id)
    ).rowcount
    db.execute(
        "UPDATE skany SET koniec=?, pominiete_pliki=?, pominiete_foldery=?, bledy_dostepu=? WHERE id=?",
        (time.time(), licz["pominiete_pliki"], licz["pominiete_foldery"], licz["bledy_dostepu"], skan_id),
    )
    db.commit()
    return {**stat, **licz, "usuniete_z_bazy": usuniete, "korzen": korzen}


if __name__ == "__main__":  # pragma: no cover
    sys.exit("Użyj: python -m katalogator skanuj <folder>")
