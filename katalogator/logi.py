"""Zapis błędów i zdarzeń do pliku oraz raport diagnostyczny do wysłania.

Plik: %LOCALAPPDATA%\\Katalogator\\logi\\katalogator.log (rotowany: 1 MB × 4 pliki).
Nieobsłużone wyjątki (także w wątkach) trafiają do dziennika zamiast okienka Windows.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import sys
import threading
import time
from pathlib import Path

LOG = logging.getLogger("katalogator")
_plik: Path | None = None


def konfiguruj(katalog: Path) -> Path:
    """Ustawia zapis do pliku (idempotentne). Zwraca ścieżkę dziennika."""
    global _plik
    folder = Path(katalog) / "logi"
    folder.mkdir(parents=True, exist_ok=True)
    plik = folder / "katalogator.log"
    if _plik == plik:
        return plik
    for h in list(LOG.handlers):
        if isinstance(h, logging.handlers.RotatingFileHandler):
            LOG.removeHandler(h)
            h.close()
    h = logging.handlers.RotatingFileHandler(plik, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s [%(threadName)s] %(message)s"))
    LOG.addHandler(h)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False
    _plik = plik

    def hak(typ, wart, tb):
        LOG.critical("Nieobsłużony błąd", exc_info=(typ, wart, tb))

    def hak_watku(a):
        if a.exc_type is not SystemExit:
            LOG.critical("Nieobsłużony błąd w wątku %s", a.thread.name if a.thread else "?",
                         exc_info=(a.exc_type, a.exc_value, a.exc_traceback))

    sys.excepthook = hak
    threading.excepthook = hak_watku
    return plik


def plik() -> Path | None:
    return _plik


def ogon(linie: int = 400) -> str:
    """Ostatnie linie dziennika (także z poprzedniego pliku po rotacji)."""
    if not _plik:
        return ""
    teksty = []
    for p in (_plik.with_name(_plik.name + ".1"), _plik):
        try:
            teksty.append(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    return "\n".join("".join(teksty).splitlines()[-linie:])


def system() -> dict:
    return {
        "system": platform.platform(),
        "python": platform.python_version(),
        "exe": bool(getattr(sys, "frozen", False)),
        "sciezka_programu": sys.executable,
        "czas": time.strftime("%Y-%m-%d %H:%M:%S"),
        "strefa": time.strftime("%z"),
        "jezyk": os.environ.get("LANG") or "",
    }
