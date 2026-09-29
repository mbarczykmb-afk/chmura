"""Folder przychodzący: nowe pliki (np. zrzucone z telefonu) trafiają do biblioteki
według tych samych zasad co główne porządkowanie.

Pliki z folderu przychodzącego są PRZENOSZONE do biblioteki (miejsca docelowego projektu).
Pliki z niepewną datą (wzięta z daty pliku) zostają w folderze przychodzącym do ręcznego
przejrzenia. Całość ma osobną bazę (przychodzace.db), więc nie miesza się z planem głównym.
Tryb automatyczny (`Katalogator.exe --auto <projekt>`) może uruchamiać Harmonogram zadań Windows.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

from . import planista, projekty, skaner, wykonawca

PREFIKS_ZADANIA = "Katalogator"


def _dom(proj: projekty.Projekty, pid: str) -> str | None:
    dane = proj.wczytaj(pid)
    if (dane.get("dom") or "").strip():
        return dane["dom"].strip()
    baza = proj.baza(pid)
    if baza.exists():  # dom wykryty w głównym planie projektu
        db = skaner.otworz_baze(baza)
        try:
            planista.przygotuj(db)
            return planista.meta(db).get("dom") or None
        finally:
            db.close()
    return None


def sprawdz(proj: projekty.Projekty, pid: str, postep=None, przerwij=None) -> dict:
    """Skanuje folder(y) przychodzące i tworzy propozycję. Nic jeszcze nie przenosi."""
    dane = proj.wczytaj(pid)
    foldery = [f for f in dane.get("przychodzace") or [] if f]
    if not foldery:
        raise ValueError("Najpierw dodaj folder przychodzący.")
    if not dane.get("cel"):
        raise ValueError("Najpierw wybierz miejsce docelowe (bibliotekę) w sekcji „Dokąd?”.")
    brak = [f for f in foldery if not os.path.isdir(f)]
    if brak:
        raise ValueError("Nie mogę otworzyć folderu: " + ", ".join(brak))
    db = skaner.otworz_baze(proj.baza_przychodzacych(pid))
    try:
        wykonawca.przygotuj(db)
        # usuń wpisy folderów, które przestały być przychodzącymi
        db.execute(f"DELETE FROM pliki WHERE korzen NOT IN ({','.join('?' * len(foldery))})",
                   [os.path.abspath(f) for f in foldery])
        for i, f in enumerate(foldery, 1):
            skaner.skanuj(f, db, postep=(lambda n, gdzie, _i=i, **_: postep and postep(
                f"skan {_i}/{len(foldery)}", n, 0, 0)), przerwij=przerwij)
        planista.generuj(db, [{"sciezka": f, "tryb": "przenies"} for f in foldery], dane["cel"],
                         postep=postep, przerwij=przerwij, dom=_dom(proj, pid))
        # niepewna data -> zostaje w folderze przychodzącym
        db.execute("UPDATE plan SET pominiety=1, uwaga=COALESCE(uwaga,'') || ' — zostaje do ręcznego przejrzenia' "
                   "WHERE tryb='przenies' AND uwaga LIKE '%data z pliku%'")
        db.commit()
        return podsumowanie(proj, pid, db)
    finally:
        db.close()


def podsumowanie(proj: projekty.Projekty, pid: str, db=None) -> dict | None:
    baza = proj.baza_przychodzacych(pid)
    if db is None and not baza.exists():
        return None
    wlasna = db is None
    db = db or skaner.otworz_baze(baza)
    try:
        wykonawca.przygotuj(db)
        if not planista.istnieje(db):
            return None
        p = planista.podsumowanie(db)
        from collections import Counter
        licz = Counter(r[0].rsplit("/", 1)[0] if "/" in r[0] else "" for r in db.execute(
            "SELECT cel FROM plan WHERE tryb='przenies' AND pominiety=0 AND stan='nowy' AND wynik IS NULL"))
        foldery = [{"folder": f, "n": n} for f, n in sorted(licz.items())]
        pominiete = [dict(nazwa=os.path.basename(r[0]), uwaga=r[1]) for r in db.execute(
            "SELECT sciezka, uwaga FROM plan WHERE tryb='przenies' AND pominiety=1 AND wynik IS NULL LIMIT 50")]
        return {**p, "foldery": foldery, "pominiete_lista": pominiete,
                "ostatnie": wykonawca.ostatnia_partia(db)}
    finally:
        if wlasna:
            db.close()


def wykonaj(proj: projekty.Projekty, pid: str, postep=None, przerwij=None) -> dict:
    db = skaner.otworz_baze(proj.baza_przychodzacych(pid))
    try:
        wykonawca.przygotuj(db)
        if not planista.istnieje(db):
            raise ValueError("Najpierw kliknij „Sprawdź nowe pliki”.")
        return wykonawca.wykonaj(db, postep=postep, przerwij=przerwij, usun_puste=True)
    finally:
        db.close()


def cofnij(proj: projekty.Projekty, pid: str, postep=None, przerwij=None) -> dict:
    db = skaner.otworz_baze(proj.baza_przychodzacych(pid))
    try:
        wykonawca.przygotuj(db)
        return wykonawca.cofnij(db, postep=postep, przerwij=przerwij)
    finally:
        db.close()


def automat(katalog: Path, pid: str) -> str:
    """Tryb bez okna (Harmonogram zadań): sprawdź + przenieś; wynik trafia do dziennika i auto.log."""
    proj = projekty.Projekty(katalog)
    start = time.strftime("%Y-%m-%d %H:%M")
    try:
        s = sprawdz(proj, pid)
        if s["przenies"]:
            w = wykonaj(proj, pid)
            opis = f"Automatycznie przeniesiono {w['zrobione']} nowych plików"
            if w["bledy"]:
                opis += f", błędy: {w['bledy']}"
        else:
            opis = "Brak nowych plików do przeniesienia"
        if s["pominiete"]:
            opis += f"; do ręcznego przejrzenia: {s['pominiete']}"
    except Exception as e:  # noqa: BLE001 — w trybie bez okna wszystko ląduje w dzienniku
        opis = f"Błąd automatycznego porządkowania: {e}"
    try:
        db = skaner.otworz_baze(proj.baza(pid))
        projekty.dopisz(db, "auto", opis)
        db.close()
        with open(proj.baza(pid).parent / "auto.log", "a", encoding="utf-8") as f:
            f.write(f"{start}  {opis}\n")
    except Exception:
        pass
    return opis


# --- Harmonogram zadań Windows -------------------------------------------------------

def _nazwa_zadania(pid: str) -> str:
    return f"{PREFIKS_ZADANIA} - {pid}"


def polecenie_programu(pid: str) -> str:
    if getattr(sys, "frozen", False):  # Katalogator.exe
        return f'"{sys.executable}" --auto {pid}'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" -m katalogator --auto {pid}'


def polecenia_harmonogramu(pid: str, godzina: str) -> list[list[str]]:
    """Polecenia schtasks: usunięcie istniejącego zadania i (opcjonalnie) utworzenie nowego."""
    nazwa = _nazwa_zadania(pid)
    usun = ["schtasks", "/Delete", "/F", "/TN", nazwa]
    if not godzina:
        return [usun]
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", godzina):
        raise ValueError("Podaj godzinę w formacie GG:MM, np. 21:00.")
    return [usun, ["schtasks", "/Create", "/F", "/SC", "DAILY", "/ST", godzina, "/TN", nazwa,
                   "/TR", polecenie_programu(pid)]]


def ustaw_harmonogram(proj: projekty.Projekty, pid: str, godzina: str) -> dict:
    godzina = (godzina or "").strip()
    polecenia = polecenia_harmonogramu(pid, godzina)
    if sys.platform != "win32":
        raise ValueError("Harmonogram działa tylko w Windows.")
    flagi = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for i, pol in enumerate(polecenia):
        w = subprocess.run(pol, capture_output=True, text=True, creationflags=flagi)
        if w.returncode != 0 and i > 0:  # błąd usunięcia (brak zadania) ignorujemy
            raise ValueError("Nie udało się utworzyć zadania: " + (w.stderr or w.stdout).strip())
    proj.zapisz(pid, {"harmonogram": godzina})
    return {"harmonogram": godzina}


def usun_wszystkie_harmonogramy(katalog: Path) -> None:
    """Przy odinstalowaniu: usuwa zadania Harmonogramu wszystkich projektów."""
    if sys.platform != "win32":
        return
    proj = projekty.Projekty(katalog)
    flagi = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for p in proj.lista():
        if p.get("harmonogram"):
            subprocess.run(polecenia_harmonogramu(p["id"], "")[0], capture_output=True, creationflags=flagi)
            proj.zapisz(p["id"], {"harmonogram": ""})
