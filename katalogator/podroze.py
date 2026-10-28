"""✈ Podróże: Google Timeline Travels (osobna aplikacja Node.js) jako zakładka Katalogatora.

Dane podróży (historia lokalizacji, trasy GPS, rezerwacje) zostają w folderze projektu na komputerze — Katalogator
ich nie kopiuje ani nie wysyła. Zakładka uruchamia `node server.js` z tego folderu (albo wykrywa już działający
serwer na tym porcie) i pokazuje aplikację w ramce. Motyw (jasny / ciemny, kolory, czcionka) przekazuje przez
parametry adresu i postMessage; opcjonalny „adapter” (jeden skrypt + styl) dopisuje się do projektu przyciskiem —
z kopią zapasową index.html — i stosuje je w aplikacji.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

LOG = logging.getLogger("katalogator.podroze")

PORT_DOMYSLNY = 8080
UI = Path(__file__).parent / "ui"
PLIKI_ADAPTERA = ("katalogator-motyw.js", "katalogator-motyw.css")
ZNACZNIK = "<!-- katalogator-motyw -->"
_BEZ_OKNA = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW

_proces: subprocess.Popen | None = None
_blokada = threading.Lock()


def domyslny_folder() -> str:
    """Typowe miejsce projektu z Antigravity — podpowiedź, gdy nic jeszcze nie ustawiono."""
    p = Path.home() / ".gemini" / "antigravity" / "scratch" / "google-timeline-travels"
    return str(p) if p.is_dir() else ""


def node() -> str | None:
    kandydaci = [os.environ.get("KATALOGATOR_NODE"), shutil.which("node")]
    if sys.platform == "win32":
        for z in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            if os.environ.get(z):
                kandydaci.append(os.path.join(os.environ[z], "nodejs", "node.exe"))
    return next((k for k in kandydaci if k and os.path.isfile(k)), None)


def sprawdz_folder(folder: str) -> str | None:
    """None, gdy to wygląda na projekt Timeline Travels; inaczej powód."""
    if not folder or not folder.strip():
        return "Wybierz folder projektu."
    p = Path(folder)
    if not p.is_dir():
        return "Nie ma takiego folderu."
    if not (p / "server.js").is_file():
        return "W tym folderze nie ma pliku server.js — wskaż główny folder projektu Google Timeline Travels."
    return None


def port_poprawny(port) -> int | None:
    try:
        p = int(port)
    except (TypeError, ValueError):
        return None
    return p if 1024 <= p <= 65535 else None


def dziala(port: int, czas: float = 1.5) -> bool:
    """Czy na tym porcie odpowiada serwer (dowolny kod HTTP)."""
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{int(port)}/", timeout=czas).close()
        return True
    except urllib.error.HTTPError:
        return True
    except (OSError, ValueError):
        return False


def _wlasny_dziala() -> bool:
    with _blokada:
        return _proces is not None and _proces.poll() is None


def stan(ust: dict) -> dict:
    """Stan dla okna: ustawienia + czy serwer działa (nasz albo uruchomiony samodzielnie)."""
    folder = ust.get("folder") or ""
    port = port_poprawny(ust.get("port")) or PORT_DOMYSLNY
    dz = dziala(port, 0.6)
    wlasny = _wlasny_dziala()
    return {"folder": folder, "podpowiedz": "" if folder else domyslny_folder(), "port": port,
            "auto": ust.get("auto", True), "node": node(), "blad_folderu": sprawdz_folder(folder) if folder else None,
            "dziala": dz, "wlasny": wlasny and dz, "zewnetrzny": dz and not wlasny,
            "adres": f"http://127.0.0.1:{port}/", "adapter": adapter_zainstalowany(folder)}


def uruchom(ust: dict, czekaj: float = 20.0) -> dict:
    """Startuje `node server.js` w folderze projektu; czeka, aż port odpowie."""
    global _proces
    port = port_poprawny(ust.get("port")) or PORT_DOMYSLNY
    if dziala(port, 0.6):
        return {"ok": True, "zewnetrzny": not _wlasny_dziala()}  # już działa (np. launch_app.bat) — nie dublujemy
    powod = sprawdz_folder(ust.get("folder") or "")
    if powod:
        return {"blad": powod}
    exe = node()
    if not exe:
        return {"blad": "Brak Node.js — zainstaluj go (nodejs.org albo: winget install OpenJS.NodeJS.LTS) i spróbuj ponownie.",
                "link": "https://nodejs.org/"}
    with _blokada:
        env = {**os.environ, "PORT": str(port)}
        try:
            _proces = subprocess.Popen([exe, "server.js"], cwd=ust["folder"], env=env, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=_BEZ_OKNA)
        except OSError as e:
            return {"blad": f"Nie udało się uruchomić serwera: {e}"}
        proces = _proces
    koniec = time.time() + czekaj
    while time.time() < koniec:
        if proces.poll() is not None:
            return {"blad": f"Serwer zakończył się od razu (kod {proces.returncode}). Uruchom w folderze projektu "
                            f"polecenie „node server.js” i sprawdź komunikat błędu."}
        if dziala(port, 0.5):
            return {"ok": True, "zewnetrzny": False}
        time.sleep(0.3)
    zatrzymaj()
    return {"blad": f"Serwer nie odpowiedział na porcie {port} w ciągu {int(czekaj)} s (port zajęty przez inny program?)."}


def zatrzymaj() -> dict:
    """Zatrzymuje tylko serwer uruchomiony przez Katalogator — cudzego (samodzielnie uruchomionego) nie ruszamy."""
    global _proces
    with _blokada:
        p, _proces = _proces, None
    if p is None or p.poll() is not None:
        return {"ok": True}
    try:
        if sys.platform == "win32":  # node potrafi zostawić procesy potomne
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, creationflags=_BEZ_OKNA,
                           timeout=10)
        else:
            p.terminate()
        p.wait(timeout=5)
    except (OSError, subprocess.SubprocessError):
        try:
            p.kill()
        except OSError:
            pass
    return {"ok": True}


# --- adapter motywu: skrypt i styl dopisywane do projektu --------------------------------------------------------------
def adapter_zainstalowany(folder: str) -> bool:
    try:
        return ZNACZNIK in (Path(folder) / "index.html").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def zainstaluj_adapter(folder: str) -> dict:
    """Kopiuje adapter do projektu i dopisuje do index.html jedną linię (z kopią index.html.katalogator.bak)."""
    powod = sprawdz_folder(folder)
    if powod:
        return {"blad": powod}
    kat = Path(folder)
    indeks = kat / "index.html"
    if not indeks.is_file():
        return {"blad": "W folderze projektu nie ma index.html."}
    try:
        html = indeks.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as e:
        return {"blad": f"Nie można odczytać index.html: {e}"}
    if ZNACZNIK in html:
        return {"ok": True, "juz": True}
    glowa = re.search(r"</head\s*>", html, re.I)
    if not glowa:
        return {"blad": "W index.html nie ma znacznika </head> — dopisz ręcznie: "
                        f'<link rel="stylesheet" href="katalogator-motyw.css"><script src="katalogator-motyw.js"></script>'}
    try:
        for n in PLIKI_ADAPTERA:
            shutil.copyfile(UI / "podroze" / n, kat / n)
        fonty = kat / "katalogator-fonty"
        fonty.mkdir(exist_ok=True)
        for f in (UI / "fonty").glob("InstrumentSans-*.woff2"):
            shutil.copyfile(f, fonty / f.name)
        kopia = kat / "index.html.katalogator.bak"
        if not kopia.exists():
            shutil.copyfile(indeks, kopia)
        wstaw = (f'{ZNACZNIK}<link rel="stylesheet" href="katalogator-motyw.css">'
                 f'<script src="katalogator-motyw.js"></script>\n')
        indeks.write_text(html[:glowa.start()] + wstaw + html[glowa.start():], encoding="utf-8")
    except OSError as e:
        return {"blad": f"Nie udało się zapisać w folderze projektu: {e}"}
    return {"ok": True, "juz": False}


def usun_adapter(folder: str) -> dict:
    kat = Path(folder)
    indeks = kat / "index.html"
    try:
        html = indeks.read_text(encoding="utf-8")
        html = re.sub(re.escape(ZNACZNIK) + r'<link rel="stylesheet" href="katalogator-motyw\.css">'
                      r'<script src="katalogator-motyw\.js"></script>\n?', "", html)
        indeks.write_text(html, encoding="utf-8")
        for n in PLIKI_ADAPTERA:
            (kat / n).unlink(missing_ok=True)
        shutil.rmtree(kat / "katalogator-fonty", ignore_errors=True)
    except OSError as e:
        return {"blad": f"Nie udało się usunąć adaptera: {e}"}
    return {"ok": True}
