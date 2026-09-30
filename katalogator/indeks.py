"""Wspólny indeks odczytów plików — to, co program raz przeczytał z dysku, służy wszystkim trybom i projektom
(Porządkowanie, Sprzątanie, Przeglądarka): metadane (data, GPS, aparat), odciski zawartości (duplikaty)
i analiza zdjęć (dokumenty, podobne, nieostre). Przez sieć to największy koszt — tak czytamy każdy plik raz.

Klucz: ścieżka + rozmiar + data modyfikacji — plik zmieniony od odczytu jest czytany od nowa.
Indeks jest tylko pamięcią podręczną: każdy błąd w nim oznacza po prostu zwykły odczyt z dysku.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

SCHEMAT = """
CREATE TABLE IF NOT EXISTS meta (
    sciezka TEXT PRIMARY KEY, rozmiar INTEGER NOT NULL, mtime REAL NOT NULL, wersja INTEGER NOT NULL,
    data TEXT, zrodlo_daty TEXT, lat REAL, lon REAL, aparat TEXT, wykonawca TEXT, album TEXT, tytul TEXT
);
CREATE TABLE IF NOT EXISTS odciski (
    sciezka TEXT PRIMARY KEY, rozmiar INTEGER NOT NULL, mtime REAL NOT NULL, szybki TEXT, pelny TEXT
);
CREATE TABLE IF NOT EXISTS analiza (
    sciezka TEXT PRIMARY KEY, rozmiar INTEGER NOT NULL, mtime REAL NOT NULL, wersja INTEGER NOT NULL,
    dhash TEXT, dokument REAL, ostrosc REAL, szer INTEGER, wys INTEGER, blad TEXT, podpis TEXT, tekst REAL
);
"""
_SCIEZKA: Path | None = None
_blokada = threading.Lock()


def ustaw(sciezka: Path | str | None) -> None:
    """Włącza wspólny indeks (plik bazy) — albo wyłącza (None)."""
    global _SCIEZKA
    _SCIEZKA = Path(sciezka) if sciezka else None
    if _SCIEZKA:
        try:
            db = _polacz()
            db.executescript(SCHEMAT)
            db.close()
        except sqlite3.Error:
            _SCIEZKA = None


def wlaczony() -> bool:
    return _SCIEZKA is not None


def _polacz() -> sqlite3.Connection:
    db = sqlite3.connect(str(_SCIEZKA), timeout=30, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout = 30000")
    if db.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
        try:
            db.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
    return db


def pobierz(tabela: str, pliki, wersja: int | None = None) -> dict[str, dict]:
    """{ścieżka: wiersz} dla plików [(ścieżka, rozmiar, mtime)], których zapis w indeksie jest aktualny."""
    if not _SCIEZKA or tabela not in ("meta", "odciski", "analiza"):
        return {}
    pliki = list(pliki)
    wynik: dict[str, dict] = {}
    try:
        db = _polacz()
        try:
            for i in range(0, len(pliki), 500):
                paczka = {p[0]: (p[1], p[2]) for p in pliki[i:i + 500]}
                for r in db.execute(f"SELECT * FROM {tabela} WHERE sciezka IN ({','.join('?' * len(paczka))})",
                                    list(paczka)):
                    r = dict(r)
                    if (r["rozmiar"], r["mtime"]) == paczka[r["sciezka"]] and (wersja is None or r.get("wersja") == wersja):
                        wynik[r["sciezka"]] = r
        finally:
            db.close()
    except sqlite3.Error:
        return {}
    return wynik


def zapisz(tabela: str, wiersze: list[dict]) -> None:
    """Dopisuje / nadpisuje wiersze (słowniki z kolumnami tabeli)."""
    if not _SCIEZKA or not wiersze or tabela not in ("meta", "odciski", "analiza"):
        return
    kol = list(wiersze[0])
    with _blokada:
        try:
            db = _polacz()
            try:
                db.executemany(f"INSERT OR REPLACE INTO {tabela}({','.join(kol)}) VALUES ({','.join('?' * len(kol))})",
                               [[w.get(k) for k in kol] for w in wiersze])
                db.commit()
            finally:
                db.close()
        except sqlite3.Error:
            pass


def uzupelnij(tabela: str, sciezka: str, **pola) -> None:
    """Zmienia pojedyncze pola istniejącego wpisu (np. pełny odcisk dopisany do szybkiego)."""
    if not _SCIEZKA or tabela not in ("odciski", "analiza") or not pola:
        return
    with _blokada:
        try:
            db = _polacz()
            try:
                db.execute(f"UPDATE {tabela} SET {', '.join(k + '=?' for k in pola)} WHERE sciezka=?",
                           [*pola.values(), sciezka])
                db.commit()
            finally:
                db.close()
        except sqlite3.Error:
            pass


def usun(sciezki: list[str]) -> None:
    """Pliki zniknęły z dysku (skasowane, przeniesione) — usuwamy je z indeksu."""
    if not _SCIEZKA or not sciezki:
        return
    with _blokada:
        try:
            db = _polacz()
            try:
                for i in range(0, len(sciezki), 500):
                    cz = sciezki[i:i + 500]
                    for t in ("meta", "odciski", "analiza"):
                        db.execute(f"DELETE FROM {t} WHERE sciezka IN ({','.join('?' * len(cz))})", cz)
                db.commit()
            finally:
                db.close()
        except sqlite3.Error:
            pass
