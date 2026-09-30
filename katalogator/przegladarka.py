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
        self._auto_watek: threading.Thread | None = None
        # galeria widzi tylko aktualnie wybrane foldery (usunięty z listy znika od razu, bez kasowania bazy)
        self.galeria = galeria.Galeria(self.baza, lambda: self.foldery(), pamiec_min=self.katalog / "miniatury",
                                       tylko_zdjecia_ludzi=True)

    # --- zestawy dysków („projekty” Przeglądarki): każdy ma własną listę dysków/folderów -------------------
    # Jedna baza na wszystkie zestawy — ten sam dysk w dwóch zestawach skanuje się raz; ulubione i albumy wspólne.
    def _plik(self) -> Path:
        return self.katalog / "zestawy.json"

    def _zestawy(self) -> dict:
        try:
            d = json.loads(self._plik().read_text(encoding="utf-8"))
            if isinstance(d, dict) and d.get("zestawy"):
                return d
        except (OSError, ValueError):
            pass
        stare = []  # do 1.9.1 jedna lista w foldery.json
        try:
            stare = [str(f) for f in json.loads((self.katalog / "foldery.json").read_text(encoding="utf-8"))]
        except (OSError, ValueError, TypeError):
            pass
        return {"aktywny": 1, "zestawy": [{"id": 1, "nazwa": "Moje dyski", "foldery": stare}]}

    def _zapisz_zestawy(self, d: dict) -> None:
        tmp = self._plik().with_suffix(".nowy")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self._plik())

    def _aktywny(self, d: dict) -> dict:
        return next((z for z in d["zestawy"] if z["id"] == d.get("aktywny")), d["zestawy"][0])

    def foldery(self) -> list[str]:
        """Dyski/foldery aktywnego zestawu."""
        return list(self._aktywny(self._zestawy())["foldery"])

    def wszystkie_foldery(self) -> list[str]:
        """Wszystkie dyski ze wszystkich zestawów (samoczynne odświeżanie)."""
        wybor = dyski.normalizuj_wybor([{"sciezka": f, "tryb": "kopiuj"}
                                        for z in self._zestawy()["zestawy"] for f in z["foldery"]])
        return [w["sciezka"] for w in wybor]

    def ustaw_foldery(self, foldery: list[str]) -> list[str]:
        wybor = dyski.normalizuj_wybor([{"sciezka": str(f), "tryb": "kopiuj"} for f in foldery if str(f).strip()])
        lista = [w["sciezka"] for w in wybor]
        d = self._zestawy()
        self._aktywny(d)["foldery"] = lista
        self._zapisz_zestawy(d)
        return lista

    def zestaw(self, akcja: str, id_: int | None = None, nazwa: str = "") -> dict:
        """akcja: nowy (i od razu aktywny) | wybierz | nazwa | usun."""
        d = self._zestawy()
        nazwa = " ".join(str(nazwa or "").split())[:60]
        z = next((x for x in d["zestawy"] if x["id"] == id_), None)
        if akcja == "nowy":
            nowy = {"id": max(x["id"] for x in d["zestawy"]) + 1, "nazwa": nazwa or "Nowy zestaw", "foldery": []}
            d["zestawy"].append(nowy)
            d["aktywny"] = nowy["id"]
        elif akcja == "wybierz" and z:
            d["aktywny"] = z["id"]
        elif akcja == "nazwa" and z and nazwa:
            z["nazwa"] = nazwa
        elif akcja == "usun" and z:
            if len(d["zestawy"]) == 1:
                return {"blad": "To jedyny zestaw — można go wyczyścić, ale nie usunąć."}
            d["zestawy"].remove(z)  # zdjęcia na dyskach zostają; znika tylko zestaw
            if d.get("aktywny") == z["id"]:
                d["aktywny"] = d["zestawy"][0]["id"]
        else:
            return {"blad": "Nieznany zestaw."}
        self._zapisz_zestawy(d)
        return self.opis()

    # --- samoczynne odświeżanie: przy starcie programu i co kilka godzin (tylko nowe/zmienione pliki) ---------
    def _ust(self) -> dict:
        try:
            d = json.loads((self.katalog / "ustawienia.json").read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _zapisz_ust(self, **zmiany) -> dict:
        d = {**self._ust(), **zmiany}
        tmp = self.katalog / "ustawienia.nowy"
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.katalog / "ustawienia.json")
        return d

    def ustaw_auto(self, auto: bool, co_godzin=None) -> dict:
        zm = {"auto": bool(auto)}
        try:
            if co_godzin is not None:
                zm["co_godzin"] = min(168.0, max(1.0, float(co_godzin)))
        except (TypeError, ValueError):
            pass
        self._zapisz_ust(**zm)
        return self.opis()

    def do_odswiezenia(self, teraz: float | None = None) -> bool:
        u = self._ust()
        if not u.get("auto", True) or not self.wszystkie_foldery():
            return False
        return (teraz or time.time()) - float(u.get("ostatni_skan", 0)) >= float(u.get("co_godzin", 6)) * 3600

    def uruchom_auto(self, pierwsze_po: float = 30, sprawdzaj_co: float = 600) -> None:
        """Wątek w tle: po starcie programu i potem co `sprawdzaj_co` s — skan, gdy minął ustawiony czas."""
        if self._auto_watek:
            return

        def petla():
            time.sleep(pierwsze_po)
            while True:
                try:
                    if self.do_odswiezenia() and not self.stan["trwa"]:
                        LOG.info("Przeglądarka: samoczynne odświeżanie")
                        self.skanuj(auto=True)
                except Exception:  # noqa: BLE001
                    LOG.exception("Przeglądarka: odświeżanie")
                time.sleep(sprawdzaj_co)
        self._auto_watek = threading.Thread(target=petla, daemon=True, name="przegladarka-auto")
        self._auto_watek.start()

    # --- skanowanie (tylko odczyt) -------------------------------------------------------------
    def opis(self) -> dict:
        with self.blokada:
            s = dict(self.stan)
        d = self._zestawy()
        s["foldery"] = list(self._aktywny(d)["foldery"])
        s["zestawy"] = [{"id": z["id"], "nazwa": z["nazwa"], "n": len(z["foldery"])} for z in d["zestawy"]]
        s["aktywny"] = self._aktywny(d)["id"]
        u = self._ust()
        s["auto"], s["co_godzin"], s["ostatni_skan"] = u.get("auto", True), u.get("co_godzin", 6), u.get("ostatni_skan")
        if s["trwa"]:
            s.update(self.tempo.wynik())
        return s

    def skanuj(self, auto: bool = False) -> str | None:
        foldery = self.wszystkie_foldery() if auto else self.foldery()
        if not foldery:
            return "Najpierw dodaj dysk albo folder."
        with self.blokada:
            if self.stan["trwa"]:
                return "Skanowanie już trwa."
            self.stan.update(trwa=True, etap="liczenie plików", zrobione=0, wszystkie=0, folder="",
                             komunikat="Odświeżam (samoczynnie)…" if auto else "Rozpoczynam…", blad="", czeka="",
                             auto=auto)
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
            self._zapisz_ust(ostatni_skan=time.time())
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
