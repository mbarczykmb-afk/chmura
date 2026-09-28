"""Projekty: osobne ustawienia, baza skanu, plan i historia — do pracy rozłożonej na wiele dni.

Układ na dysku (domyślnie %LOCALAPPDATA%\\Katalogator):
    projekty/<id>/projekt.json   nazwa, notatki, źródła, cel, folder przychodzący…
    projekty/<id>/katalog.db     skan, duplikaty, analiza, plan, dziennik
    projekty/<id>/przychodzace.db   osobna baza dla automatycznego porządkowania
    ostatni.json                 ostatnio otwarty projekt
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import sqlite3
import time
import unicodedata
from pathlib import Path

DOMYSLNE = {"nazwa": "Mój projekt", "notatki": "", "zrodla": [], "cel": "", "przychodzace": [],
            "dom": "", "harmonogram": ""}

SCHEMAT_DZIENNIKA = """
CREATE TABLE IF NOT EXISTS dziennik (czas REAL NOT NULL, typ TEXT NOT NULL, opis TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS przejrzane (folder TEXT PRIMARY KEY, czas REAL NOT NULL);
"""


def _slug(nazwa: str) -> str:
    s = unicodedata.normalize("NFKD", nazwa).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:30] or "projekt"
    return f"{s}-{secrets.token_hex(3)}"


class Projekty:
    def __init__(self, katalog: Path):
        self.katalog = Path(katalog)
        self.folder = self.katalog / "projekty"
        self.folder.mkdir(parents=True, exist_ok=True)
        self._migruj()

    # --- lista / tworzenie ---------------------------------------------------
    def _migruj(self) -> None:
        """Wersje < 1.1 trzymały ustawienia i bazę bezpośrednio w katalogu programu."""
        stare_ust, stara_baza = self.katalog / "ustawienia.json", self.katalog / "katalog.db"
        if not (stare_ust.exists() or stara_baza.exists()) or any(self.folder.iterdir()):
            return
        dane = {}
        try:
            dane = json.loads(stare_ust.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        pid = self.nowy("Mój pierwszy projekt", {"zrodla": dane.get("zrodla", []), "cel": dane.get("cel", "")})
        if stara_baza.exists():
            shutil.move(str(stara_baza), str(self.folder / pid / "katalog.db"))
        if stare_ust.exists():
            stare_ust.rename(self.katalog / "ustawienia.json.przeniesione")

    def lista(self) -> list[dict]:
        wynik = []
        for p in self.folder.iterdir():
            plik = p / "projekt.json"
            if not plik.is_file():
                continue
            try:
                d = {**DOMYSLNE, **json.loads(plik.read_text(encoding="utf-8")), "id": p.name}
            except (OSError, ValueError):
                continue
            d["statystyki"] = self._statystyki(p / "katalog.db")
            wynik.append(d)
        wynik.sort(key=lambda d: -(d.get("ostatnio") or 0))
        return wynik

    @staticmethod
    def _statystyki(baza: Path) -> dict:
        st = {"pliki": 0, "foldery": 0, "przejrzane": 0, "uporzadkowane": 0, "rozmiar": 0}
        if not baza.exists():
            return st
        try:
            db = sqlite3.connect(f"file:{baza}?mode=ro", uri=True)
            tabele = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "pliki" in tabele:
                st["pliki"], st["rozmiar"] = db.execute("SELECT COUNT(*), COALESCE(SUM(rozmiar),0) FROM pliki").fetchone()
            if "plan" in tabele:
                foldery = {r[0].rsplit("/", 1)[0] for r in db.execute(
                    "SELECT cel FROM plan WHERE tryb!='istniejacy' AND pominiety=0 AND instr(cel,'/')>0")}
                st["foldery"] = len(foldery)
                st["uporzadkowane"] = db.execute("SELECT COUNT(*) FROM plan WHERE wynik='ok'").fetchone()[0]
                if "przejrzane" in tabele:
                    st["przejrzane"] = len(foldery & {r[0] for r in db.execute("SELECT folder FROM przejrzane")})
            db.close()
        except sqlite3.Error:
            pass
        return st

    def nowy(self, nazwa: str, dane: dict | None = None) -> str:
        nazwa = (nazwa or "").strip()[:80] or "Nowy projekt"
        pid = _slug(nazwa)
        (self.folder / pid).mkdir(parents=True)
        teraz = time.time()
        self.zapisz(pid, {**DOMYSLNE, **(dane or {}), "nazwa": nazwa, "utworzono": teraz, "ostatnio": teraz})
        return pid

    def wczytaj(self, pid: str) -> dict:
        plik = self._folder(pid) / "projekt.json"
        return {**DOMYSLNE, **json.loads(plik.read_text(encoding="utf-8")), "id": pid}

    def zapisz(self, pid: str, dane: dict) -> dict:
        folder = self._folder(pid, musi_istniec=False)
        folder.mkdir(parents=True, exist_ok=True)
        plik = folder / "projekt.json"
        try:
            obecne = json.loads(plik.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            obecne = {}
        nowe = {**DOMYSLNE, **obecne, **{k: v for k, v in dane.items() if k != "id"}}
        tmp = plik.with_suffix(".tmp")
        tmp.write_text(json.dumps(nowe, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(plik)
        return {**nowe, "id": pid}

    def usun(self, pid: str) -> None:
        """Usuwa tylko dane projektu (ustawienia, bazę) — nigdy Twoich plików."""
        shutil.rmtree(self._folder(pid))

    def _folder(self, pid: str, musi_istniec: bool = True) -> Path:
        if not re.fullmatch(r"[a-z0-9\-]{1,64}", pid or ""):
            raise ValueError("Nieprawidłowy projekt.")
        f = self.folder / pid
        if musi_istniec and not (f / "projekt.json").is_file():
            raise ValueError("Nie ma takiego projektu.")
        return f

    def baza(self, pid: str) -> Path:
        return self._folder(pid) / "katalog.db"

    def baza_przychodzacych(self, pid: str) -> Path:
        return self._folder(pid) / "przychodzace.db"

    # --- ostatnio otwarty ---------------------------------------------------------
    def ostatni(self) -> str | None:
        try:
            pid = json.loads((self.katalog / "ostatni.json").read_text(encoding="utf-8"))["id"]
            self._folder(pid)
            return pid
        except (OSError, ValueError, KeyError):
            lista = self.lista()
            return lista[0]["id"] if lista else None

    def ustaw_ostatni(self, pid: str) -> None:
        (self.katalog / "ostatni.json").write_text(json.dumps({"id": pid}), encoding="utf-8")
        self.zapisz(pid, {"ostatnio": time.time()})


# --- dziennik i przejrzane foldery (w bazie projektu) ---------------------------------

def przygotuj(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMAT_DZIENNIKA)


def dopisz(db: sqlite3.Connection, typ: str, opis: str) -> None:
    przygotuj(db)
    db.execute("INSERT INTO dziennik VALUES (?,?,?)", (time.time(), typ, opis))
    db.commit()


def dziennik(db: sqlite3.Connection, ile: int = 50) -> list[dict]:
    przygotuj(db)
    wpisy = [dict(czas=r[0], typ=r[1], opis=r[2]) for r in db.execute(
        "SELECT czas, typ, opis FROM dziennik ORDER BY czas DESC LIMIT ?", (ile,))]
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='plan_ops'").fetchone():
        wpisy += [dict(czas=r[0], typ="edycja", opis=r[1] + (" (cofnięte)" if r[2] else "")) for r in db.execute(
            "SELECT czas, opis, cofnieta FROM plan_ops ORDER BY czas DESC LIMIT ?", (ile,))]
    wpisy.sort(key=lambda w: -w["czas"])
    return wpisy[:ile]


def oznacz_przejrzany(db: sqlite3.Connection, folder: str, wartosc: bool = True) -> dict:
    przygotuj(db)
    folder = folder.strip("/")
    if wartosc:
        db.execute("INSERT OR REPLACE INTO przejrzane VALUES (?,?)", (folder, time.time()))
    else:
        db.execute("DELETE FROM przejrzane WHERE folder=?", (folder,))
    db.commit()
    return {"folder": folder, "przejrzany": wartosc}


def przejrzane(db: sqlite3.Connection) -> set[str]:
    przygotuj(db)
    return {r[0] for r in db.execute("SELECT folder FROM przejrzane")}
