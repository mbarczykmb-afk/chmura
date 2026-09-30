"""Skanowanie folderów do lokalnej bazy SQLite (wznawialne)."""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import indeks, typy
from .metadane import Metadane, boczne_nazwy, odczytaj

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


WERSJA_ODCZYTU = 2  # 1.4: GPS i data z XMP oraz plików .json/.xmp obok zdjęć


def otworz_baze(sciezka: str | Path) -> sqlite3.Connection:
    """Połączenie z bazą projektu. Tryb WAL: odczyt (np. odświeżanie okna) nigdy nie czeka na zapis
    zadania w tle, a zapis czeka do 30 s na zakończenie cudzej transakcji zamiast od razu zgłaszać
    „database is locked”."""
    db = sqlite3.connect(str(sciezka), timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=30000")
    if str(sciezka) != ":memory:":
        # Przełączenie na WAL potrzebuje wyłącznej blokady i nie czeka na innych — robimy je tylko raz
        # (tryb zapisuje się w pliku bazy), a gdy baza jest akurat zajęta, ponawiamy chwilę później.
        for proba in range(50):
            try:
                if db.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
                    db.execute("PRAGMA journal_mode=WAL")
                break
            except sqlite3.OperationalError:
                if proba == 49:
                    raise
                time.sleep(0.1)
        db.execute("PRAGMA synchronous=NORMAL")
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


def _przejdz(korzen: str, licz: dict, straznik=None, nieczytelne: list | None = None, pomijaj=frozenset()):
    """Rekurencyjnie zwraca (ścieżka, nazwa, stat) z pominięciem śmieci (i folderów z `pomijaj`, małymi literami)."""
    stos = [korzen]
    while stos:
        folder = stos.pop()
        try:
            wpisy = list(straznik.wykonaj(os.scandir, folder, folder)) if straznik else list(os.scandir(folder))
        except OSError:
            licz["bledy_dostepu"] += 1
            if nieczytelne is not None:
                nieczytelne.append(folder)
            continue
        for w in wpisy:
            try:
                if w.is_dir(follow_symlinks=False):
                    if typy.pominac_folder(w.name) or w.name.lower() in pomijaj:
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
           postep=None, przerwij=None, straznik=None, pomijaj=frozenset()) -> dict:
    """Dwa etapy: 1) lista plików (szybko, daje liczbę do paska postępu), 2) odczyt metadanych
    nowych i zmienionych plików. postep(liczba_plikow, folder, wszystkie=…, etap=…) — co ok. 0,5 s;
    przerwij — threading.Event; straznik — stabilnosc.Straznik (czekanie na dysk sieciowy)."""
    from .stabilnosc import Straznik
    korzen = os.path.abspath(korzen)
    if not os.path.isdir(korzen):
        raise NotADirectoryError(korzen)
    straznik = straznik or Straznik([korzen], przerwij)
    cur = db.execute("INSERT INTO skany(korzen, start) VALUES (?, ?)", (korzen, time.time()))
    skan_id = cur.lastrowid
    db.commit()  # nie trzymaj blokady zapisu podczas przeglądania folderów
    db.execute("CREATE TABLE IF NOT EXISTS skaner_meta (klucz TEXT PRIMARY KEY, wartosc TEXT)")
    w = db.execute("SELECT wartosc FROM skaner_meta WHERE klucz = ?", ("wersja:" + korzen,)).fetchone()
    aktualne = bool(w) and int(w[0]) >= WERSJA_ODCZYTU  # starsza wersja: czytamy nagłówki jeszcze raz (np. GPS z XMP)
    znane = {
        r["sciezka"]: (r["rozmiar"], r["mtime"])
        for r in db.execute("SELECT sciezka, rozmiar, mtime FROM pliki WHERE korzen = ? AND blad IS NULL",
                            (korzen,))
    } if aktualne else {}
    licz = {"pominiete_pliki": 0, "pominiete_foldery": 0, "bledy_dostepu": 0}
    stat = {"wszystkie": 0, "nowe_lub_zmienione": 0, "bez_zmian": 0}
    niezmienione: list[str] = []
    nieczytelne: list[str] = []
    do_odczytu: list = []
    ostatni_wydruk = time.time()

    def zglos(n, gdzie, wszystkie=0, etap="", wymus=False):
        nonlocal ostatni_wydruk
        teraz = time.time()
        if postep is not None and (wymus or teraz - ostatni_wydruk > 0.5):
            try:
                postep(n, gdzie, wszystkie=wszystkie, etap=etap)
            except TypeError:  # starsze wywołania: postep(n, gdzie)
                postep(n, gdzie)
            ostatni_wydruk = teraz
        elif postep is None and teraz - ostatni_wydruk > 2:
            wypisz(f"  ...{etap or 'przejrzano'}: {n} plików")
            ostatni_wydruk = teraz

    # 1) lista plików (przy okazji: pliki towarzyszące .json/.xmp — źródło GPS i daty)
    boczne: dict[str, str] = {}
    for el in _przejdz(korzen, licz, straznik, nieczytelne, pomijaj):
        stat["wszystkie"] += 1
        sciezka, nazwa_el, st = el
        if nazwa_el.lower().endswith((".json", ".xmp")):
            boczne[os.path.normcase(sciezka)] = sciezka
        if znane.get(sciezka) == (st.st_size, st.st_mtime):
            stat["bez_zmian"] += 1
            niezmienione.append(sciezka)
        else:
            do_odczytu.append(el)
        if przerwij is not None and przerwij.is_set():
            raise Przerwano(korzen)
        zglos(stat["wszystkie"], os.path.dirname(sciezka), etap="liczenie plików")
    stat["nowe_lub_zmienione"] = len(do_odczytu)
    # wspólny indeks: pliki już przeczytane w innym trybie / projekcie nie są czytane z dysku drugi raz
    z_indeksu = indeks.pobierz("meta", [(e[0], e[2].st_size, e[2].st_mtime) for e in do_odczytu], WERSJA_ODCZYTU)
    do_indeksu: list[dict] = []

    def zadanie(el):
        sciezka, nazwa, st = el
        if przerwij is not None and przerwij.is_set():
            return None
        rodz = typy.rodzaj(nazwa)
        b = [boczne[k] for k in (os.path.normcase(x) for x in boczne_nazwy(sciezka)) if k in boczne] if boczne else None
        zi = z_indeksu.get(sciezka) if not b else None  # z plikami .json/.xmp obok — zawsze świeży odczyt
        if zi:
            m = Metadane()
            for k in ("zrodlo_daty", "lat", "lon", "aparat", "wykonawca", "album", "tytul"):
                setattr(m, k, zi[k])
            if zi["data"]:
                from datetime import datetime
                m.data = datetime.fromisoformat(zi["data"])
            return sciezka, st, rodz, m
        m = odczytaj(sciezka, rodz, st.st_mtime, b)
        if m.blad and not os.path.exists(sciezka) and straznik.korzen(sciezka):
            # błąd odczytu, bo zniknął dysk? poczekaj na niego i spróbuj jeszcze raz
            if straznik.czekaj_na(straznik.korzen(sciezka)):
                m = odczytaj(sciezka, rodz, st.st_mtime, b)
        return sciezka, st, rodz, m

    def zapisz(wynik):
        sciezka, st, rodz, m = wynik
        if not m.blad and sciezka not in z_indeksu and indeks.wlaczony():
            do_indeksu.append({"sciezka": sciezka, "rozmiar": st.st_size, "mtime": st.st_mtime, "wersja": WERSJA_ODCZYTU,
                               "data": m.data.isoformat(timespec="seconds") if m.data else None,
                               "zrodlo_daty": m.zrodlo_daty, "lat": m.lat, "lon": m.lon, "aparat": m.aparat,
                               "wykonawca": m.wykonawca, "album": m.album, "tytul": m.tytul})
        db.execute(
            "INSERT OR REPLACE INTO pliki VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sciezka, korzen, os.path.relpath(sciezka, korzen), st.st_size, st.st_mtime,
                rodz, Path(sciezka).suffix.lower(),
                m.data.isoformat(timespec="seconds") if m.data else None, m.zrodlo_daty,
                m.lat, m.lon, m.aparat, m.wykonawca, m.album, m.tytul, m.blad, skan_id,
            ),
        )

    # 2) metadane nowych i zmienionych (paczkami — pamięć i blokada bazy pozostają małe)
    zglos(0, korzen, len(do_odczytu), "odczyt metadanych", wymus=True)
    zrobione = 0
    with ThreadPoolExecutor(max_workers=watki) as pula:
        for i in range(0, len(do_odczytu), 256):
            paczka = do_odczytu[i:i + 256]
            for wynik in pula.map(zadanie, paczka):
                if wynik is not None:
                    zapisz(wynik)
                    zrobione += 1
            db.commit()
            indeks.zapisz("meta", do_indeksu)
            do_indeksu.clear()
            if przerwij is not None and przerwij.is_set():
                raise Przerwano(korzen)
            zglos(zrobione, os.path.dirname(paczka[-1][0]), len(do_odczytu), "odczyt metadanych")
    zglos(zrobione, korzen, len(do_odczytu), "odczyt metadanych", wymus=True)

    # Oznacz pliki bez zmian jako widziane w tym skanie, usuń te, których już nie ma.
    for i in range(0, len(niezmienione), 500):
        paczka = niezmienione[i:i + 500]
        db.execute(
            f"UPDATE pliki SET skan = ? WHERE sciezka IN ({','.join('?' * len(paczka))})",
            [skan_id, *paczka],
        )
    # folderów, których nie dało się odczytać, nie traktujemy jak usuniętych
    for f in nieczytelne:
        pref = f.rstrip("\\/") + os.sep
        db.execute("UPDATE pliki SET skan = ? WHERE korzen = ? AND substr(sciezka, 1, ?) = ?",
                   (skan_id, korzen, len(pref), pref))
    if indeks.wlaczony():  # plików, których już nie ma, nie trzymamy też we wspólnym indeksie
        indeks.usun([r[0] for r in db.execute("SELECT sciezka FROM pliki WHERE korzen = ? AND skan != ?",
                                              (korzen, skan_id))])
    usuniete = db.execute(
        "DELETE FROM pliki WHERE korzen = ? AND skan != ?", (korzen, skan_id)
    ).rowcount
    db.execute("INSERT OR REPLACE INTO skaner_meta VALUES (?, ?)", ("wersja:" + korzen, str(WERSJA_ODCZYTU)))
    db.execute(
        "UPDATE skany SET koniec=?, pominiete_pliki=?, pominiete_foldery=?, bledy_dostepu=? WHERE id=?",
        (time.time(), licz["pominiete_pliki"], licz["pominiete_foldery"], licz["bledy_dostepu"], skan_id),
    )
    db.commit()
    return {**stat, **licz, "usuniete_z_bazy": usuniete, "korzen": korzen, "nieczytelne": nieczytelne}


if __name__ == "__main__":  # pragma: no cover
    sys.exit("Użyj: python -m katalogator skanuj <folder>")
