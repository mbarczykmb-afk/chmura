"""Powiadomienie o nowej wersji: sprawdza najnowsze wydanie na GitHubie (najwyżej co 12 h).

Wysyłane jest tylko zwykłe zapytanie o listę wydań (bez żadnych danych o Tobie i Twoich plikach).
Sprawdzanie można wyłączyć w „O programie”.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from . import __version__
from .logi import LOG

REPO = "mbarczykmb-afk/chmura"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
CO_ILE = 12 * 3600


def wersja_krotka(tekst: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", tekst or "")[:3]) or (0,)


def _ustawienia(katalog: Path) -> dict:
    try:
        return json.loads((katalog / "program.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def zapisz_ustawienia(katalog: Path, **zmiany) -> dict:
    d = {**_ustawienia(katalog), **zmiany}
    (katalog / "program.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return d


def wlaczone(katalog: Path) -> bool:
    return _ustawienia(katalog).get("sprawdzaj_aktualizacje", True)


def _pobierz_info(timeout: float = 6) -> dict:
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": f"Katalogator/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def sprawdz(katalog: Path, wymus: bool = False, pobierz=None) -> dict:
    """{"biezaca", "najnowsza", "nowa": bool, "url_instalatora", "url_strony", "opis", "blad"}."""
    wynik = {"biezaca": __version__, "najnowsza": None, "nowa": False, "url_instalatora": None,
             "url_strony": f"https://github.com/{REPO}/releases", "opis": "", "blad": None,
             "wlaczone": wlaczone(katalog)}
    if not wymus and not wynik["wlaczone"]:
        return wynik
    pamiec = katalog / "aktualizacje.json"
    try:
        zapis = json.loads(pamiec.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        zapis = {}
    if not wymus and zapis.get("czas", 0) > time.time() - CO_ILE and zapis.get("info"):
        info = zapis["info"]
    else:
        try:
            info = (pobierz or _pobierz_info)()
            pamiec.write_text(json.dumps({"czas": time.time(), "info": info}), encoding="utf-8")
        except Exception as e:  # brak internetu, brak wydań (404), limit zapytań…
            LOG.info("Nie udało się sprawdzić aktualizacji: %s", e)
            wynik["blad"] = "Nie udało się sprawdzić (brak internetu albo jeszcze brak wydań)."
            return wynik
    tag = info.get("tag_name") or ""
    wynik["najnowsza"] = tag.lstrip("v")
    wynik["nowa"] = wersja_krotka(tag) > wersja_krotka(__version__)
    wynik["url_strony"] = info.get("html_url") or wynik["url_strony"]
    wynik["opis"] = (info.get("body") or "")[:1500]
    for a in info.get("assets") or []:
        if re.search(r"setup.*\.exe$", a.get("name", ""), re.I):
            wynik["url_instalatora"] = a.get("browser_download_url")
    return wynik


def pobierz_i_uruchom(url: str, postep=None, przerwij=None) -> Path:
    """Pobiera instalator do katalogu tymczasowego i uruchamia go (program potem się zamyka)."""
    if not url or not url.startswith("https://github.com/"):
        raise ValueError("Nieprawidłowy adres instalatora.")
    cel = Path(tempfile.gettempdir()) / os.path.basename(url.split("?")[0])
    req = urllib.request.Request(url, headers={"User-Agent": f"Katalogator/{__version__}"})
    with urllib.request.urlopen(req, timeout=30) as r, open(cel, "wb") as f:
        razem = int(r.headers.get("Content-Length") or 0)
        pobrane = 0
        while True:
            if przerwij is not None and przerwij.is_set():
                raise InterruptedError("Przerwano pobieranie.")
            k = r.read(1 << 20)
            if not k:
                break
            f.write(k)
            pobrane += len(k)
            if postep:
                postep("pobieranie instalatora", pobrane, razem, pobrane)
    if sys.platform == "win32":
        subprocess.Popen([str(cel)], close_fds=True)
    LOG.info("Uruchomiono instalator %s", cel)
    return cel
