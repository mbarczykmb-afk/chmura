"""Bezpieczny odczyt i zapis małych plików JSON z ustawieniami (projekt, program, Przeglądarka).

Windows potrafi chwilowo zablokować plik (antywirus, indeksowanie, równoległa podmiana przez inny wątek), a zanik
prądu może zostawić plik w połowie zapisu. Zasady:
- odczyt ponawia próbę przy blokadzie; uszkodzony plik → kopia .bak; brak pliku → None;
- istniejący, ale nieczytelny plik → wyjątek — NIGDY wartości domyślne, bo następny zapis nadpisałby nimi
  wszystkie ustawienia (tak „znikał” projekt z własną nazwą);
- zapis: plik tymczasowy (unikalny dla wątku) + fsync + os.replace z ponowieniem, potem kopia .bak.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

BLOKADA = threading.RLock()   # wspólna dla wszystkich plików ustawień — zapisy są krótkie i rzadkie


def czytaj(plik: Path, proby: int = 6):
    """Zawartość pliku albo None, gdy pliku (ani kopii) nie ma."""
    plik = Path(plik)
    for i in range(proby):
        try:
            return json.loads(plik.read_text(encoding="utf-8"))
        except FileNotFoundError:
            break
        except ValueError:
            break
        except OSError:
            if i == proby - 1:
                raise
            time.sleep(0.05 * (i + 1))
    try:
        return json.loads(plik.with_name(plik.name + ".bak").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        if plik.exists() and plik.stat().st_size:
            raise ValueError(f"Plik ustawień jest uszkodzony: {plik}")
        return None


def zapisz(plik: Path, dane, wciecie: int | None = 2) -> None:
    plik = Path(plik)
    tekst = json.dumps(dane, ensure_ascii=False, indent=wciecie)
    with BLOKADA:
        tmp = plik.with_name(f"{plik.name}.{threading.get_ident()}.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(tekst)
            f.flush()
            os.fsync(f.fileno())
        for i in range(6):   # Windows: podmiana pliku otwartego przez czytelnika chwilowo się nie udaje
            try:
                os.replace(tmp, plik)
                break
            except PermissionError:
                if i == 5:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                    raise
                time.sleep(0.05 * (i + 1))
        try:
            plik.with_name(plik.name + ".bak").write_text(tekst, encoding="utf-8")
        except OSError:
            pass


def zmien(plik: Path, **zmiany) -> dict:
    """Odczyt + scalenie + zapis pod jedną blokadą (dwa wątki nie zgubią sobie nawzajem zmian)."""
    with BLOKADA:
        d = {**(czytaj(plik) or {}), **zmiany}
        zapisz(plik, d)
        return d
