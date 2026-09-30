"""Przeglądarka dysków: wybrane dyski/foldery są tylko skanowane (nic nie jest zmieniane) i pokazywane
na osi czasu i mapie. Osobna baza — niezależna od projektów porządkowania."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from . import dyski, galeria, skaner, stabilnosc
from .logi import LOG


# Całe dyski (np. C:) — foldery systemu i programów są pełne ikon i grafik, nie zdjęć
FOLDERY_SYSTEMOWE = frozenset({"windows", "program files", "program files (x86)", "programdata", "appdata",
                               "$windows.~bt", "$windows.~ws", "windows.old", "msocache", "intel", "amd", "nvidia",
                               "node_modules", "site-packages", "__pycache__", "application data",
                               "local settings", "perflogs", "recovery", "boot"})


class Przegladarka:
    def __init__(self, katalog: Path):
        self.katalog = Path(katalog) / "przegladarka"
        self.katalog.mkdir(parents=True, exist_ok=True)
        self.baza = self.katalog / "katalog.db"
        self.blokada = threading.Lock()
        self.przerwij = threading.Event()
        self.stan = {"trwa": False, "etap": "", "zrobione": 0, "wszystkie": 0, "folder": "", "komunikat": "",
                     "blad": "", "czeka": ""}
        self.tempo = stabilnosc.Tempo()
        # galeria widzi tylko aktualnie wybrane foldery (usunięty z listy znika od razu, bez kasowania bazy)
        self.galeria = galeria.Galeria(self.baza, lambda: self.foldery(), pamiec_min=self.katalog / "miniatury",
                                       tylko_zdjecia_ludzi=True)

    # --- wybrane foldery -----------------------------------------------------------------
    def _plik(self) -> Path:
        return self.katalog / "foldery.json"

    def foldery(self) -> list[str]:
        try:
            return [str(f) for f in json.loads(self._plik().read_text(encoding="utf-8"))]
        except (OSError, ValueError, TypeError):
            return []

    def ustaw_foldery(self, foldery: list[str]) -> list[str]:
        wybor = dyski.normalizuj_wybor([{"sciezka": str(f), "tryb": "kopiuj"} for f in foldery if str(f).strip()])
        lista = [w["sciezka"] for w in wybor]
        tmp = self._plik().with_suffix(".nowy")
        tmp.write_text(json.dumps(lista, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self._plik())
        return lista

    # --- skanowanie (tylko odczyt) -------------------------------------------------------------
    def opis(self) -> dict:
        with self.blokada:
            s = dict(self.stan)
        s["foldery"] = self.foldery()
        if s["trwa"]:
            s.update(self.tempo.wynik())
        return s

    def skanuj(self) -> str | None:
        foldery = self.foldery()
        if not foldery:
            return "Najpierw dodaj dysk albo folder."
        with self.blokada:
            if self.stan["trwa"]:
                return "Skanowanie już trwa."
            self.stan.update(trwa=True, etap="liczenie plików", zrobione=0, wszystkie=0, folder="",
                             komunikat="Rozpoczynam…", blad="", czeka="")
            self.tempo = stabilnosc.Tempo()
        self.przerwij.clear()
        threading.Thread(target=self._skanuj, args=(foldery,), daemon=True, name="przegladarka").start()
        return None

    def _skanuj(self, foldery: list[str]) -> None:
        db = skaner.otworz_baze(self.baza)
        t0, plikow, pominiete = time.time(), 0, []

        def czeka(tekst):
            with self.blokada:
                self.stan["czeka"] = tekst or ""
        straznik = stabilnosc.Straznik(foldery, self.przerwij, czeka)
        try:
            with stabilnosc.Czuwanie():
                for i, folder in enumerate(foldery, 1):
                    if not os.path.isdir(folder):
                        pominiete.append(folder)
                        continue

                    def postep(n, gdzie, wszystkie=0, etap="", _i=i):
                        with self.blokada:
                            self.stan.update(zrobione=n, wszystkie=wszystkie, folder=gdzie, etap=etap,
                                             komunikat=f"Dysk / folder {_i} z {len(foldery)}")
                            if wszystkie:
                                self.tempo.dodaj(min(1.0, n / wszystkie), n, 0)
                    w = skaner.skanuj(folder, db, postep=postep, przerwij=self.przerwij, straznik=straznik,
                                      wypisz=lambda *_: None, pomijaj=FOLDERY_SYSTEMOWE)
                    plikow += w.get("wszystkie", 0)
            k = f"Gotowe — przejrzano {plikow:,} plików w {time.time() - t0:.0f} s.".replace(",", " ")
            if pominiete:
                k += " Niedostępne: " + ", ".join(pominiete)
            with self.blokada:
                self.stan.update(trwa=False, komunikat=k, etap="", czeka="")
        except skaner.Przerwano:
            db.commit()
            with self.blokada:
                self.stan.update(trwa=False, komunikat="Przerwano — to, co przejrzane, jest już widoczne.",
                                 etap="", czeka="")
        except Exception as e:  # noqa: BLE001 — błąd pokazujemy w oknie, szczegóły w dzienniku
            LOG.exception("Przeglądarka: błąd skanowania")
            with self.blokada:
                self.stan.update(trwa=False, blad=str(e), etap="", czeka="")
        finally:
            db.close()
