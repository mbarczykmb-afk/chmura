"""Aplikacja okienkowa: lokalny serwer + interfejs HTML w oknie Edge (tryb aplikacji).

Serwer słucha tylko na 127.0.0.1 i wymaga losowego tokenu, więc inne strony
ani komputery w sieci nie mają do niego dostępu.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import (__version__, aktualizacje, analiza, duplikaty, dyski, filmy, galeria, indeks, logi, lokalizacja, pilot, planista, projekty, przegladarka,
               przychodzace, raport, kategorie, skaner, sprzatanie, stabilnosc, usuwanie, wykonawca)
from .logi import LOG

UI = Path(__file__).parent / "ui"
BEZ_PINGU_ZAMKNIJ_PO = 150  # s; przeglądarka spowalnia timery w zminimalizowanym oknie


def katalog_danych() -> Path:
    baza = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    k = Path(baza) / "Katalogator"
    k.mkdir(parents=True, exist_ok=True)
    return k


class Stan:
    def __init__(self, katalog: Path):
        self.katalog = katalog
        self.projekty = projekty.Projekty(katalog)
        self.blokada = threading.Lock()
        self.przerwij = threading.Event()
        self.ostatni_ping = time.time()
        self.wersja_danych = 0          # rośnie po każdej zmianie danych
        self._podsumowania = (-1, {})   # (wersja, dane) — okno pyta o stan co sekundę
        self._licze_podsumowania = threading.Lock()
        self.tempa: dict[str, stabilnosc.Tempo] = {}
        self._galerie: dict = {}
        # wspólny indeks odczytów: Porządkowanie, Sprzątanie i Przeglądarka czytają każdy plik z dysku raz
        indeks.ustaw(Path(katalog) / "wspolny_indeks.db")
        self.przegladarka = przegladarka.Przegladarka(katalog)  # dyski do oglądania, osobna baza
        self.serwer_tel = None
        pid = self.projekty.ostatni() or self.projekty.nowy("Mój projekt")
        self._otworz(pid)

    def galeria(self, zakres: str = "biblioteka") -> "galeria.Galeria":
        """Przeglądarka biblioteki: „biblioteka” = miejsce docelowe, „wszystko” = całe dane projektu."""
        if zakres == "przegladarka":  # dowolne dyski, niezależnie od projektu
            return self.przegladarka.galeria
        klucz = (str(self.baza), zakres)
        g = self._galerie.get(klucz)
        if g is None:
            korzenie = (lambda: [self.ustawienia["cel"]] if self.ustawienia["cel"] else []) \
                if zakres == "biblioteka" else (lambda: None)
            g = self._galerie[klucz] = galeria.Galeria(self.baza, korzenie,  # miniatury zapamiętane na dysku
                                                       pamiec_min=Path(self.katalog) / "miniatury" / "galeria")
        return g

    def telefon(self, wlacz: bool, zakres: str = "biblioteka", sterowanie: bool = True,
                pin: str | None = None) -> dict:
        """Telefon (PIN; sieć domowa albo Tailscale): stan pracy, kolejne kroki (gdy `sterowanie`) i galeria.
        `pin`: własny PIN (4–12 cyfr, zapamiętany na stałe), "" = losowy przy każdym włączeniu, None = bez zmian."""
        if pin is not None:
            pin = pin.strip()
            if pin and not (pin.isdigit() and 4 <= len(pin) <= 12):
                return {"blad": "PIN to 4–12 cyfr."}
            aktualizacje.zapisz_ustawienia(self.katalog, pin_telefonu=pin)
        ust = aktualizacje._ustawienia(self.katalog)
        wlasny = ust.get("pin_telefonu") or None
        staly = None
        if wlasny:  # token zależny od PIN-u: zmiana PIN-u wylogowuje telefony, restart programu — nie
            sekret = ust.get("sekret_telefonu")
            if not sekret:
                sekret = secrets.token_hex(16)
                aktualizacje.zapisz_ustawienia(self.katalog, sekret_telefonu=sekret)
            staly = hmac.new(sekret.encode(), wlasny.encode(), hashlib.sha256).hexdigest()
        with self.blokada:
            if self.serwer_tel is not None and wlacz:  # już działa — zmieniamy tylko sterowanie (i PIN)
                s = self.serwer_tel
                s.pilot.sterowanie = sterowanie
                aktualizacje.zapisz_ustawienia(self.katalog, telefon_auto={"zakres": zakres, "sterowanie": sterowanie})
                if pin is not None:
                    s.pin = wlasny or galeria.losowy_pin()
                    s.staly_token = staly
                    s.tokeny.clear()  # nowy PIN — telefony logują się od nowa
                return self._tel_info(s, sterowanie, wlasny)
            if self.serwer_tel is not None:
                self.serwer_tel.stop()
                self.serwer_tel = None
            if not wlacz:
                aktualizacje.zapisz_ustawienia(self.katalog, telefon_auto=None)
                return {"wlaczone": False}
            for port in (8765, 8766, 8767, 0):
                try:
                    self.serwer_tel = galeria.SerwerGalerii(self.galeria(zakres), port=port, pin=wlasny, staly_token=staly,
                                                            pilot=pilot.Pilot(self, sterowanie),
                                                            galerie=self.galeria).start()
                    break
                except OSError:
                    continue
            s = self.serwer_tel
        LOG.info("Udostępnianie na telefon: %s", s.adresy())
        aktualizacje.zapisz_ustawienia(self.katalog, telefon_auto={"zakres": zakres, "sterowanie": sterowanie})
        return self._tel_info(s, sterowanie, wlasny)

    @staticmethod
    def _tel_info(s, sterowanie: bool, wlasny) -> dict:
        return {"wlaczone": True, "pin": s.pin, "wlasny_pin": bool(wlasny), "adresy": s.adresy(), "port": s.port,
                "sterowanie": sterowanie, "autostart": autostart(), "autostart_mozliwy": autostart_mozliwy()}

    def telefon_po_starcie(self) -> None:
        """Telefon był włączony przy poprzednim zamknięciu — włączamy od razu (ten sam PIN, ten sam adres)."""
        a = aktualizacje._ustawienia(self.katalog).get("telefon_auto")
        if isinstance(a, dict):
            try:
                self.telefon(True, str(a.get("zakres") or "biblioteka"), bool(a.get("sterowanie", True)))
            except Exception:
                LOG.exception("Nie udało się włączyć telefonu po starcie")

    def telefon_wlaczony(self) -> bool:
        return self.serwer_tel is not None

    def _otworz(self, pid: str) -> None:
        self.projekt = self.projekty.wczytaj(pid)
        self.pid = pid
        self.baza = self.projekty.baza(pid)
        self.ustawienia = {"zrodla": dyski.normalizuj_wybor(self.projekt.get("zrodla") or []),
                           "cel": self.projekt.get("cel") or ""}
        self.skan = {"trwa": False, "przejrzano": 0, "wszystkie": 0, "etap": "", "folder": "", "komunikat": "",
                     "blad": ""}
        self.dup = {"trwa": False, "etap": "", "zrobione": 0, "wszystkie": 0, "bajty": 0, "bajty_razem": 0,
                    "komunikat": "", "blad": ""}
        self.zad = {n: self._pusty() for n in ("analiza", "plan", "wykonanie", "przychodzace", "aktualizacja",
                                               "usuwanie")}
        self.miniatury: dict[int, bytes] = {}
        self.projekty.ustaw_ostatni(pid)
        self.wersja_danych += 1
        self._ustaw_kosz()

    def otworz_projekt(self, pid: str) -> str | None:
        if self.zajety():
            return "Poczekaj, aż skończy się bieżące zadanie."
        try:
            self._otworz(pid)
        except ValueError as e:
            return str(e)
        return None

    def rozeslij_lokalizacje(self, zakres: str, w: dict) -> None:
        """📍 Zmiana lokalizacji widoczna od razu wszędzie: w pozostałych projektach i w Przeglądarce."""
        bazy = [self.projekty.baza(p["id"]) for p in self.projekty.lista()] + [self.przegladarka.baza]
        zrodlo = self.przegladarka.baza if zakres == "przegladarka" else self.baza
        for b in bazy:
            if os.path.abspath(str(b)) != os.path.abspath(str(zrodlo)) and os.path.exists(b):
                lokalizacja.rozeslij(b, w["sciezki"], w.get("lat"), w.get("lon"))

    def przelacz_tryb(self, tryb: str) -> str | None:
        """Porządkowanie ↔ Sprzątanie: otwiera ostatni projekt danego rodzaju (albo zakłada nowy)."""
        if tryb not in ("porzadkowanie", "sprzatanie"):
            return "Nieznany tryb."
        if self.projekt.get("typ", "porzadkowanie") == tryb:
            return None
        pid = next((p["id"] for p in self.projekty.lista() if p.get("typ", "porzadkowanie") == tryb), None)
        if pid is None:
            pid = self.projekty.nowy("Sprzątanie dysku" if tryb == "sprzatanie" else "Mój projekt", {"typ": tryb})
        blad = self.otworz_projekt(pid)
        if not blad:
            self.projekty.ustaw_ostatni(pid)
        return blad

    def korzenie_kosza(self) -> list[str]:
        """Foldery, w których może leżeć kosz (Odłożone): wybrane foldery i miejsce docelowe."""
        k = [z["sciezka"] for z in self.ustawienia["zrodla"]]
        cel = self.ustawienia.get("cel")
        if cel and os.path.isdir(cel) and not any(dyski.zawiera(z, cel) for z in k):
            k.append(cel)
        return k

    def kosz_w_celu(self) -> str | None:
        """Porządkowanie z miejscem docelowym: wszystko, co odkładasz, trafia do <cel>/Odłożone (jeden kosz)."""
        if (self.projekt.get("typ") or "porzadkowanie") == "porzadkowanie" and self.ustawienia.get("cel"):
            return self.ustawienia["cel"]
        return None

    def _ustaw_kosz(self) -> None:
        try:
            self.z_db(duplikaty.ustaw_kosz, self.kosz_w_celu())
        except Exception:
            LOG.exception("Nie udało się ustawić kosza")

    def przenies_kosz(self) -> str | None:
        """Istniejące foldery Odłożone ze źródeł → <cel>/Odłożone (z zachowaniem „Cofnij”)."""
        cel = self.kosz_w_celu()
        if not cel or not os.path.isdir(cel):
            return "Najpierw wybierz dostępne miejsce docelowe („Dokąd?”)."
        zrodla = [z["sciezka"] for z in self.ustawienia["zrodla"]]

        def f(db, postep, przerwij):
            w = sprzatanie.przenies_do_celu(db, zrodla, cel, postep, przerwij)
            if not w["wszystkie"]:
                return "W folderach źródłowych nie ma już nic w „Odłożone”."
            k = (f"Przeniesiono {w['przeniesione']} plików ({raport.rozmiar_txt(w['bajty'])}) "
                 f"do {os.path.join(cel, duplikaty.FOLDER_ODLOZONE)}.")
            if w["bledy"]:
                k += f" Nie udało się: {len(w['bledy'])} (np. {w['bledy'][0]})."
            return k
        return self.uruchom("usuwanie", f)

    def usun_partie(self, partia: int) -> str | None:
        def f(db, postep, przerwij):
            w = sprzatanie.usun_partie(db, partia, postep, przerwij)
            k = f"Usunięto na stałe {w['usuniete']} plików ({raport.rozmiar_txt(w['bajty'])})."
            if w["bledy"]:
                k += f" Nie udało się usunąć: {len(w['bledy'])} (np. {w['bledy'][0]})."
            return k
        return self.uruchom("usuwanie", f)

    def usun_odlozone(self, kategorie_: list[str] | None, puste: bool) -> str | None:
        korzenie = self.korzenie_kosza()

        def f(db, postep, przerwij):
            w = sprzatanie.usun_odlozone(db, korzenie, kategorie_, postep, przerwij)
            k = f"Usunięto na stałe {w['usuniete']} plików ({raport.rozmiar_txt(w['bajty'])})."
            if puste:
                n = sprzatanie.usun_puste_foldery(korzenie)
                k += f" Usunięto pustych folderów: {n}." if n else ""
            if w["bledy"]:
                k += f" Nie udało się usunąć: {len(w['bledy'])} (np. {w['bledy'][0]})."
            return k
        wynik = self.uruchom("usuwanie", f)
        self.przegladarka.zglos_zmiany()
        return wynik

    def zmien_projekt(self, dane: dict) -> dict:
        pid = dane.get("id") or self.pid
        zmiany = {k: str(dane[k])[:20000] for k in ("nazwa", "notatki", "dom") if k in dane}
        if "nazwa" in zmiany and not zmiany["nazwa"].strip():
            return {"blad": "Nazwa nie może być pusta."}
        wynik = self.projekty.zapisz(pid, zmiany)
        if pid == self.pid:
            self.projekt = wynik
        return wynik

    def usun_projekt(self, pid: str) -> str | None:
        if pid == self.pid:
            if self.zajety():
                return "Poczekaj, aż skończy się bieżące zadanie."
            inne = [p["id"] for p in self.projekty.lista() if p["id"] != pid]
            self._otworz(inne[0] if inne else self.projekty.nowy("Mój projekt"))
        try:
            self.projekty.usun(pid)
        except (ValueError, OSError) as e:
            return str(e)
        return None

    def dziennik(self, typ: str, opis: str) -> None:
        try:
            db = skaner.otworz_baze(self.baza)
            try:
                projekty.dopisz(db, typ, opis)
            finally:
                db.close()
        except Exception:
            pass

    def zmiana(self) -> None:
        with self.blokada:
            self.wersja_danych += 1

    @staticmethod
    def _pusty() -> dict:
        return {"trwa": False, "etap": "", "zrobione": 0, "wszystkie": 0, "bajty": 0, "komunikat": "", "blad": ""}

    def zapisz_ustawienia(self, dane: dict) -> None:
        zrodla = dyski.normalizuj_wybor(dane.get("zrodla") or [])
        cel = str(dane.get("cel", "")).strip()
        self.ustawienia = {"zrodla": zrodla, "cel": os.path.normpath(cel) if cel else ""}
        zmiany = dict(self.ustawienia)
        if "przychodzace" in dane:
            zmiany["przychodzace"] = [os.path.normpath(str(p)) for p in dane["przychodzace"] if str(p).strip()]
        self.projekt = self.projekty.zapisz(self.pid, zmiany)
        self._ustaw_kosz()

    def ma_wyniki(self) -> bool:
        if not self.baza.exists():
            return False
        db = skaner.otworz_baze(self.baza)
        try:
            return db.execute("SELECT 1 FROM pliki LIMIT 1").fetchone() is not None
        finally:
            db.close()

    def db(self):
        db = skaner.otworz_baze(self.baza)
        wykonawca.przygotuj(db)  # tworzy też tabele duplikatów, analizy i planu
        projekty.przygotuj(db)
        return db

    def stan(self) -> dict:
        with self.blokada:
            skan, dup = dict(self.skan), dict(self.dup)
        ma = self.ma_wyniki()
        with self.blokada:
            zad = {k: dict(v) for k, v in self.zad.items()}
        dane = {"wersja": __version__, "windows": dyski.WINDOWS, "sep": os.sep, **self.ustawienia, "skan": skan,
                "projekt": {k: self.projekt.get(k) for k in ("id", "nazwa", "notatki", "przychodzace", "dom",
                                                             "harmonogram", "typ")},
                "dup": dup, "zad": zad, "ma_wyniki": ma, "duplikaty": None, "do_cofniecia": None,
                "analiza": None, "plan": None, "wykonanie": None, "przychodzace": None}
        dane["biezace"] = self._biezace(skan, dup, zad)
        dane["ffmpeg"] = bool(filmy.ffmpeg())
        with self.przegladarka.blokada:  # skan Przeglądarki (także samoczynny w tle) — dla wskaźnika pracy
            ps = self.przegladarka.stan
            dane["przegladarka"] = {k: ps.get(k) for k in ("trwa", "zrobione", "wszystkie", "etap", "auto")}
        ust = aktualizacje._ustawienia(self.katalog)
        dane["powitanie_widziane"] = bool(ust.get("powitanie_widziane"))
        dane["motyw"] = ust.get("motyw", "dark")
        if ma:
            with self.blokada:
                wersja, (w_cache, cache) = self.wersja_danych, self._podsumowania
            # W trakcie zadania pokazujemy ostatnie podsumowania (przy 50 tys. plików liczenie ich co sekundę
            # spowalniało zadanie i okno — wątki zadania zajmują procesor); po zakończeniu zadania wersja
            # danych rośnie i liczymy od nowa.
            # Liczy tylko jeden wątek naraz — pozostałe zapytania dostają poprzedni wynik.
            if w_cache != wersja and not dane["biezace"] and self._licze_podsumowania.acquire(blocking=False):
                # Liczymy w osobnym wątku; czekamy najwyżej 1,5 s — przy dużym projekcie okno pokazuje się od razu,
                # a podsumowania dochodzą przy następnym odświeżeniu.
                wynik: dict = {}

                def licz():
                    try:
                        wynik.update(self._przelicz_podsumowania(wersja))
                        self._blad_podsumowan = None
                    except Exception as e:
                        LOG.exception("Nie udało się policzyć podsumowań")
                        self._blad_podsumowan = f"{type(e).__name__}: {e}"
                    finally:
                        self._licze_podsumowania.release()
                w = threading.Thread(target=licz, daemon=True)
                w.start()
                w.join(0.25)  # okno nie czeka — wyniki dojdą przy następnym odświeżeniu
                if not w.is_alive():
                    cache = wynik
            dane["wczytuje"] = self._licze_podsumowania.locked() and w_cache < 0
            dane["blad_wczytania"] = getattr(self, "_blad_podsumowan", None) if w_cache < 0 else None
            dane.update(cache)
        return dane

    def _przelicz_podsumowania(self, wersja: int) -> dict:
        cache = {}
        db = self.db()
        try:
            if duplikaty.szukano(db):
                cache["duplikaty"] = duplikaty.podsumowanie(db)
            cache["do_cofniecia"] = duplikaty.ostatnia_partia(db)
            if db.execute("SELECT 1 FROM analiza LIMIT 1").fetchone():
                cache["analiza"] = analiza.podsumowanie(db)
            if planista.istnieje(db):
                cache["plan"] = planista.podsumowanie(db)
            cache["nie_z_aparatu"] = sum(1 for p in kategorie.do_sprawdzenia(db) if not p["decyzja"])
            cache["plikow"] = db.execute("SELECT COUNT(*) FROM pliki").fetchone()[0]
            cache["wykonanie"] = wykonawca.ostatnia_partia(db)
        finally:
            db.close()
        try:
            cache["przychodzace"] = przychodzace.podsumowanie(self.projekty, self.pid)
        except Exception:
            cache["przychodzace"] = None
        with self.blokada:
            self._podsumowania = (wersja, cache)
        return cache

    NAZWY_ZADAN = {"skan": "Skanowanie", "dup": "Szukanie duplikatów", "analiza": "Analiza zdjęć",
                   "plan": "Tworzenie propozycji", "wykonanie": "Porządkowanie plików",
                   "przychodzace": "Folder przychodzący", "aktualizacja": "Aktualizacja",
                   "usuwanie": "Usuwanie odłożonych plików"}

    def _biezace(self, skan: dict, dup: dict, zad: dict) -> dict | None:
        """Jedno trwające zadanie w jednolitej postaci — dla paska postępu u góry okna."""
        if skan["trwa"]:
            nazwa, z = "skan", {"etap": skan.get("etap") or "", "zrobione": skan.get("zrobione", 0),
                                "wszystkie": skan.get("wszystkie", 0), "plik": skan.get("folder", ""),
                                "czeka": skan.get("czeka"), "opis": skan.get("komunikat", "")}
        elif dup["trwa"]:
            nazwa, z = "dup", dup
        else:
            nazwa = next((n for n, v in zad.items() if v["trwa"]), None)
            if nazwa is None:
                return None
            z = zad[nazwa]
        w = {"nazwa": nazwa, "tytul": self.NAZWY_ZADAN.get(nazwa, nazwa)}
        for k in ("etap", "zrobione", "wszystkie", "bajty", "bajty_razem", "plik", "czeka", "opis"):
            if z.get(k):
                w[k] = z[k]
        t = self.tempa.get(nazwa)
        if t:
            w.update(t.wynik())
        return w

    def _tempo(self, nazwa: str, z: dict) -> None:
        """Zapisz próbkę postępu (pod blokadą) — z niej liczymy prędkość i czas do końca."""
        t = self.tempa.get(nazwa)
        if t is None:
            return
        klucz = (z.get("etap"), z.get("wszystkie"), z.get("bajty_razem"))
        if getattr(t, "klucz", None) != klucz:  # nowy etap — liczymy tempo od nowa
            t.probki.clear()
            t.klucz = klucz
        if z.get("bajty_razem"):
            u = min(1.0, (z.get("bajty") or 0) / z["bajty_razem"])
        elif z.get("wszystkie"):
            u = min(1.0, (z.get("zrobione") or 0) / z["wszystkie"])
        else:
            return
        t.dodaj(u, z.get("zrobione") or 0, z.get("bajty") or 0)

    def _zajety(self) -> bool:  # wywoływać pod blokadą
        return self.skan["trwa"] or self.dup["trwa"] or any(z["trwa"] for z in self.zad.values())

    def zajety(self) -> bool:
        with self.blokada:
            return self._zajety()

    def uruchom(self, nazwa: str, funkcja) -> str | None:
        """Zadanie w tle: funkcja(db, postep, przerwij) -> komunikat."""
        with self.blokada:
            if self._zajety():
                return "Poczekaj, aż skończy się bieżące zadanie."
            self.zad[nazwa] = {**self._pusty(), "trwa": True, "etap": "przygotowanie"}
            self.tempa[nazwa] = stabilnosc.Tempo()
        self.przerwij.clear()

        def praca():
            db = self.db()

            def postep(etap, zrobione, wszystkie, bajty, **dod):
                with self.blokada:
                    z = self.zad[nazwa]
                    if etap != z.get("etap"):
                        z.pop("bajty_razem", None)
                        z.pop("plik", None)
                    z.update(etap=etap, zrobione=zrobione, wszystkie=wszystkie, bajty=bajty, **dod)
                    self._tempo(nazwa, z)

            def czeka(tekst):
                with self.blokada:
                    self.zad[nazwa]["czeka"] = tekst
            postep.czeka = czeka
            try:
                with stabilnosc.Czuwanie():
                    komunikat, blad = funkcja(db, postep, self.przerwij), ""
            except skaner.Przerwano:
                komunikat, blad = "Przerwano. Postęp zapisany — możesz dokończyć później.", ""
            except Exception as e:
                LOG.exception("Zadanie „%s” nie powiodło się", nazwa)
                komunikat, blad = "Nie powiodło się.", f"{e}" if isinstance(e, (OSError, ValueError)) else \
                    f"{type(e).__name__}: {e}"
            finally:
                db.close()
            with self.blokada:
                self.zad[nazwa].update(trwa=False, komunikat=komunikat, blad=blad)
                self.wersja_danych += 1
            self.dziennik(nazwa, komunikat + (" " + blad if blad else ""))
            LOG.info("Zadanie „%s”: %s %s", nazwa, komunikat, blad)
            if nazwa in ("wykonanie", "cofanie", "przychodzace", "usuwanie"):
                self.przegladarka.zglos_zmiany()  # pliki zmieniły miejsce — Przeglądarka odświeży się sama

        threading.Thread(target=praca, daemon=True).start()
        return None

    # --- skan w tle ----------------------------------------------------
    def rozpocznij_skan(self) -> str | None:
        foldery = [z["sciezka"] for z in self.ustawienia["zrodla"]]
        cel = self.ustawienia["cel"]
        if not foldery:
            return "Najpierw wybierz folder do uporządkowania."
        brak = [f for f in foldery if not os.path.isdir(f)]
        if brak:
            return "Nie mogę otworzyć folderu: " + ", ".join(brak)
        # miejsce docelowe też skanujemy (o ile już istnieje i nie leży w źródle) — nowy folder powstanie przy porządkowaniu
        if cel and os.path.isdir(cel) and not any(dyski.zawiera(z, cel) for z in foldery):
            foldery.append(cel)
        with self.blokada:
            if self._zajety():
                return "Poczekaj, aż skończy się bieżące zadanie."
            self.skan = {"trwa": True, "przejrzano": 0, "wszystkie": 0, "etap": "liczenie plików", "folder": "",
                         "komunikat": "Rozpoczynam…", "blad": ""}
            self.tempa["skan"] = stabilnosc.Tempo()
        self.przerwij.clear()
        threading.Thread(target=self._skanuj, args=(foldery,), daemon=True).start()
        return None

    def _skanuj(self, foldery: list[str]) -> None:
        db = skaner.otworz_baze(self.baza)
        razem = 0

        def czeka(tekst):
            with self.blokada:
                self.skan["czeka"] = tekst
        straznik = stabilnosc.Straznik(foldery, self.przerwij, czeka)
        nieczytelne: list[str] = []
        try:
            with stabilnosc.Czuwanie():
                for i, folder in enumerate(foldery, 1):
                    def postep(n, gdzie, wszystkie=0, etap="", _i=i, _baza=razem):
                        with self.blokada:
                            if etap == "liczenie plików":  # przejrzano = wszystkie znalezione pliki
                                self.skan.update(przejrzano=_baza + n)
                            self.skan.update(zrobione=n, wszystkie=wszystkie, folder=gdzie, etap=etap,
                                             komunikat=f"Folder {_i} z {len(foldery)}")
                            self._tempo("skan", {"etap": (etap, _i), "zrobione": n, "wszystkie": wszystkie})
                    w = skaner.skanuj(folder, db, postep=postep, przerwij=self.przerwij, straznik=straznik)
                    razem += w["wszystkie"]
                    with self.blokada:
                        self.skan["przejrzano"] = razem
                    nieczytelne += w.get("nieczytelne") or []
            # foldery odznaczone od poprzedniego skanu: ich pliki znikają z listy projektu (decyzje zostają
            # zapamiętane — po ponownym zaznaczeniu folderu wrócą)
            wybrane = [os.path.abspath(f) for f in foldery]  # tak zapisuje je skaner
            stare = [r[0] for r in db.execute(
                f"SELECT DISTINCT korzen FROM pliki WHERE korzen NOT IN ({','.join('?' * len(wybrane))})", wybrane)]
            usuniete = 0
            for k in stare:
                usuniete += db.execute("DELETE FROM pliki WHERE korzen = ?", (k,)).rowcount
            db.commit()
            komunikat, blad = f"Gotowe — przejrzano {razem} plików.", ""
            if usuniete:
                komunikat += (f" Z listy zniknęło {usuniete} plików z folderów, których już nie wybrano "
                              f"({', '.join(stare[:3])}{'…' if len(stare) > 3 else ''}).")
                LOG.info("Usunięto z projektu %s plików z niewybranych folderów: %s", usuniete, stare)
            if nieczytelne:
                komunikat += (f" Nie udało się otworzyć {len(nieczytelne)} folderów (np. {nieczytelne[0]}) — "
                              "ich wcześniejsze wyniki zostały zachowane.")
                LOG.warning("Nieczytelne foldery przy skanie: %s", nieczytelne[:50])
        except skaner.Przerwano:
            komunikat, blad = "Przerwano. Postęp zapisany — kolejny skan dokończy resztę.", ""
        except Exception as e:  # pokaż błąd w oknie zamiast cichej awarii
            LOG.exception("Skan nie powiódł się")
            komunikat, blad = "Skan nie powiódł się.", f"{type(e).__name__}: {e}"
        finally:
            db.close()
        with self.blokada:
            self.skan.update(trwa=False, komunikat=komunikat, blad=blad)
            self.wersja_danych += 1
        self.dziennik("skan", komunikat + (" " + blad if blad else ""))

    # --- duplikaty w tle --------------------------------------------------
    def szukaj_duplikatow(self) -> str | None:
        if not self.ma_wyniki():
            return "Najpierw zeskanuj foldery."
        with self.blokada:
            if self._zajety():
                return "Poczekaj, aż skończy się bieżące zadanie."
            self.dup = {"trwa": True, "etap": "przygotowanie", "zrobione": 0, "wszystkie": 0, "bajty": 0,
                        "bajty_razem": 0, "komunikat": "", "blad": ""}
            self.tempa["dup"] = stabilnosc.Tempo()
        self.przerwij.clear()
        threading.Thread(target=self._duplikaty, daemon=True).start()
        return None

    def _duplikaty(self) -> None:
        db = self.db()

        def postep(etap, zrobione, wszystkie, bajty, **dod):
            with self.blokada:
                self.dup.update(etap=etap, zrobione=zrobione, wszystkie=wszystkie, bajty=bajty, **dod)
                self._tempo("dup", self.dup)

        def czeka(tekst):
            with self.blokada:
                self.dup["czeka"] = tekst
        postep.czeka = czeka
        try:
            with stabilnosc.Czuwanie():
                w = duplikaty.szukaj(db, postep=postep, przerwij=self.przerwij)
            komunikat = (f"Znaleziono {w['nadmiar']} zbędnych kopii ({raport.rozmiar_txt(w['bajty'])})."
                         if w["nadmiar"] else "Nie znaleziono duplikatów.")
            komunikat, blad = komunikat + (f" Uwaga: {w['problemy']}." if w.get("problemy") else ""), ""
        except skaner.Przerwano:
            komunikat, blad = ("Przerwano. Sprawdzone pliki są zapamiętane — wznowienie zacznie od miejsca przerwania. "
                               "Największe pliki (filmy, archiwa) są sprawdzane na końcu, więc dalsza część "
                               "idzie wolniej w liczbie plików; przerwany duży plik sprawdzany jest od początku."), ""
        except Exception as e:
            LOG.exception("Wyszukiwanie duplikatów nie powiodło się")
            komunikat, blad = "Wyszukiwanie nie powiodło się.", f"{type(e).__name__}: {e}"
        finally:
            db.close()
        with self.blokada:
            self.dup.update(trwa=False, komunikat=komunikat, blad=blad)
            self.wersja_danych += 1
        self.dziennik("duplikaty", komunikat + (" " + blad if blad else ""))

    def grupy(self, rodzaj: str | None, od: int, ile: int) -> dict:
        db = self.db()
        try:
            cele = {os.path.abspath(self.ustawienia["cel"])} if self.ustawienia["cel"] else set()
            grupy = duplikaty.grupy(db, rodzaj or None, od, ile, cele)
            kat = kategorie.kategorie_plikow(db, [f["id"] for g in grupy for f in g["pliki"]])
            for g in grupy:
                g["kat"] = next((kat[f["id"]] for f in g["pliki"] if f["id"] in kat), None)
            return {"grupy": grupy, "podsumowanie": duplikaty.podsumowanie(db),
                    "przejrzane": duplikaty.ile_przejrzanych(db, "dup")}
        finally:
            db.close()

    def przenies_duplikaty(self, decyzje: list) -> dict:
        if self.zajety():
            return {"blad": "Poczekaj, aż skończy się bieżące zadanie."}
        db = self.db()
        try:
            return duplikaty.przenies(db, decyzje)
        finally:
            db.close()
            self.przegladarka.zglos_zmiany()

    def cofnij(self) -> dict:
        if self.zajety():
            return {"blad": "Poczekaj, aż skończy się bieżące zadanie."}
        db = self.db()
        try:
            return duplikaty.cofnij(db)
        finally:
            db.close()
            self.przegladarka.zglos_zmiany()

    # --- miniatury: pamięć na dysku (<dane>/miniatury, do 1,5 GB) + przygotowywanie z wyprzedzeniem ---------------
    # Przez sieć (My Cloud) każda miniatura to odczyt z dysku sieciowego — robimy ją raz, a listę (duplikaty,
    # podobne, dokumenty) przygotowujemy w tle, zanim okno poprosi o kolejne obrazki.
    MAKS_PAMIEC_MIN = 1_500_000_000

    def _plik_miniatury(self, sciezka: str, rozmiar, mtime, srednia: bool) -> Path:
        import hashlib
        k = hashlib.sha1(f"{sciezka}|{rozmiar}|{mtime}|{'s' if srednia else 'm'}".encode()).hexdigest()
        return Path(self.katalog) / "miniatury" / k[:2] / f"{k}.jpg"

    def _wiersz_zdjecia(self, id_: int):
        db = self.db()
        try:
            r = db.execute("SELECT sciezka, rozmiar, mtime FROM pliki WHERE rowid=? AND rodzaj='zdjecie'", (id_,)).fetchone()
            if not r:  # plik z planu, którego nie ma już w skanie (np. w miejscu docelowym)
                r = db.execute("SELECT sciezka, rozmiar, NULL mtime FROM plan WHERE plik_id=? AND rodzaj='zdjecie'",
                               (id_,)).fetchone()
        finally:
            db.close()
        return r

    def miniatura(self, id_: int, srednia: bool = False, wiersz=None) -> bytes | None:
        klucz = ("s", id_) if srednia else id_
        if klucz in self.miniatury:
            return self.miniatury[klucz]
        r = wiersz or self._wiersz_zdjecia(id_)
        if not r:
            return None
        plik = self._plik_miniatury(r["sciezka"], r["rozmiar"], r["mtime"], srednia)
        try:
            dane = plik.read_bytes()
        except OSError:
            dane = None
        if dane is None:
            try:
                import io
                if srednia:  # do porównywania podobnych — wyraźniejsza niż miniatura z EXIF
                    im, _ = analiza.miniatura(r["sciezka"], min_bok=200)
                    im.thumbnail((600, 600))
                else:
                    im, _ = analiza.miniatura(r["sciezka"], min_bok=150)
                    im.thumbnail((260, 260))
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=82)
                dane = buf.getvalue()
            except Exception:
                return None
            try:
                plik.parent.mkdir(parents=True, exist_ok=True)
                tmp = plik.with_suffix(".tmp")
                tmp.write_bytes(dane)
                os.replace(tmp, plik)
                self._nowych_min = getattr(self, "_nowych_min", 0) + 1
                if self._nowych_min % 2000 == 0:
                    threading.Thread(target=self._przytnij_miniatury, daemon=True).start()
            except OSError:
                pass
        if len(self.miniatury) > 600:
            self.miniatury.clear()
        self.miniatury[klucz] = dane
        return dane

    def _przytnij_miniatury(self) -> None:
        try:
            pliki = [(p.stat().st_atime, p.stat().st_size, p) for p in (Path(self.katalog) / "miniatury").rglob("*.jpg")]
        except OSError:
            return
        razem = sum(r for _, r, _ in pliki)
        for _, r, p in sorted(pliki):
            if razem <= self.MAKS_PAMIEC_MIN * 0.8:
                break
            try:
                p.unlink()
                razem -= r
            except OSError:
                pass

    def przygotuj_miniatury(self, ids, srednia: bool = False) -> None:
        """Miniatury listy w tle (3 wątki, najpierw te z góry listy) — okno dostaje je potem od razu."""
        with self.blokada:
            if not hasattr(self, "_kolejka_min"):
                import collections
                self._kolejka_min, self._w_kolejce, self._watki_min = collections.deque(), set(), 0
            nowe = [(int(i), srednia) for i in ids if (int(i), srednia) not in self._w_kolejce]
            self._kolejka_min.extendleft(reversed(nowe))  # najnowsza lista ma pierwszeństwo
            self._w_kolejce.update(nowe)
            while len(self._kolejka_min) > 3000:  # stare, nieobejrzane — porzucamy
                self._w_kolejce.discard(self._kolejka_min.pop())
            uruchom = min(3 - self._watki_min, len(self._kolejka_min))
            self._watki_min += max(0, uruchom)
        for _ in range(max(0, uruchom)):
            threading.Thread(target=self._watek_miniatur, daemon=True, name="miniatury").start()

    def _watek_miniatur(self) -> None:
        while True:
            with self.blokada:
                if not self._kolejka_min:
                    self._watki_min -= 1
                    return
                id_, srednia = self._kolejka_min.popleft()
                self._w_kolejce.discard((id_, srednia))
            if self._zajety():  # trwa skan / porządkowanie — dysk jest potrzebny zadaniu
                time.sleep(0.5)
            try:
                self.miniatura(id_, srednia)
            except Exception:
                pass

    def sciezka_filmu(self, id_: int) -> str | None:
        db = self.db()
        try:
            r = db.execute("SELECT sciezka FROM pliki WHERE rowid=? AND rodzaj='film'", (id_,)).fetchone() or \
                db.execute("SELECT sciezka FROM plan WHERE plik_id=? AND rodzaj='film'", (id_,)).fetchone()
        finally:
            db.close()
        return r["sciezka"] if r else None

    def miniatura_filmu(self, id_: int) -> bytes | None:
        """Klatka filmu (ffmpeg — każdy format), zapamiętana na dysku: <dane>/miniatury_filmow/."""
        import hashlib
        sc = self.sciezka_filmu(id_)
        if not sc:
            return None
        try:
            st = os.stat(sc)
        except OSError:
            return None
        k = hashlib.sha1(f"{sc}|{st.st_size}|{st.st_mtime}".encode()).hexdigest()
        plik = Path(self.katalog) / "miniatury_filmow" / f"{k}.jpg"
        try:
            return plik.read_bytes()
        except OSError:
            pass
        jpeg = filmy.klatka(sc, 480)
        if jpeg:
            try:
                plik.parent.mkdir(exist_ok=True)
                plik.write_bytes(jpeg)
            except OSError:
                pass
        return jpeg

    def podglad(self, id_: int) -> bytes | None:
        """Duży podgląd zdjęcia (np. do porównania podobnych) — bez zapamiętywania."""
        db = self.db()
        try:
            r = db.execute("SELECT sciezka FROM pliki WHERE rowid=? AND rodzaj='zdjecie'", (id_,)).fetchone()
        finally:
            db.close()
        if not r:
            return None
        try:
            import io
            im = analiza._obraz_do_tekstu(r["sciezka"], bok=1400)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=85)
            return buf.getvalue()
        except Exception:
            LOG.info("Brak podglądu dla %s", r["sciezka"], exc_info=True)
            return None

    # --- zadania: analiza, plan, wykonanie ---------------------------------------
    def analizuj(self) -> str | None:
        if not self.ma_wyniki():
            return "Najpierw zeskanuj foldery."

        def f(db, postep, przerwij):
            w = analiza.analizuj(db, postep=postep, przerwij=przerwij)
            return (f"Przeanalizowano {w['przeanalizowane']} zdjęć: możliwych dokumentów {w['dokumenty']}, "
                    f"grup podobnych {w['podobne_grupy']}.")
        return self.uruchom("analiza", f)

    def generuj_plan(self) -> str | None:
        if not self.ma_wyniki():
            return "Najpierw zeskanuj foldery."
        if not self.ustawienia["cel"]:
            return "Najpierw wybierz miejsce docelowe („Dokąd?”)."
        zrodla, cel = list(self.ustawienia["zrodla"]), self.ustawienia["cel"]

        def f(db, postep, przerwij):
            w = planista.generuj(db, zrodla, cel, postep=postep, przerwij=przerwij)
            return f"Propozycja gotowa: {w['kopiuj'] + w['przenies']} plików do uporządkowania."
        return self.uruchom("plan", f)

    def wykonaj(self, usun_puste: bool, usun_oryginaly: bool = True) -> str | None:
        def f(db, postep, przerwij):
            w = wykonawca.wykonaj(db, postep=postep, przerwij=przerwij, usun_puste=usun_puste,
                                  usun_oryginaly=usun_oryginaly)
            k = f"Gotowe: {w['zrobione']} plików ({raport.rozmiar_txt(w['bajty'])})."
            if w["bledy"]:
                k += f" Błędy: {w['bledy']} — szczegóły w drzewie (czerwone)."
            if w["usuniete_foldery"]:
                k += f" Usunięto pustych folderów: {w['usuniete_foldery']}."
            return k
        return self.uruchom("wykonanie", f)

    def cofnij_wykonanie(self) -> str | None:
        def f(db, postep, przerwij):
            w = wykonawca.cofnij(db, postep=postep, przerwij=przerwij)
            k = f"Cofnięto {w['cofniete']} plików. Przeskanuj foldery, żeby odświeżyć wyniki."
            if w["bledy"]:
                k += " Problemy: " + "; ".join(w["bledy"][:5])
            return k
        return self.uruchom("wykonanie", f)

    def przychodzace_zadanie(self, co: str) -> str | None:
        pid = self.pid

        def f(db, postep, przerwij):
            if co == "sprawdz":
                w = przychodzace.sprawdz(self.projekty, pid, postep=postep, przerwij=przerwij)
                return (f"Nowe pliki: {w['przenies']} do przeniesienia" +
                        (f", {w['pominiete']} zostaje do ręcznego przejrzenia" if w["pominiete"] else "") + ".")
            if co == "wykonaj":
                w = przychodzace.wykonaj(self.projekty, pid, postep=postep, przerwij=przerwij)
                return f"Przeniesiono do biblioteki {w['zrobione']} plików" + (
                    f", błędy: {w['bledy']}." if w["bledy"] else ".")
            w = przychodzace.cofnij(self.projekty, pid, postep=postep, przerwij=przerwij)
            return f"Cofnięto {w['cofniete']} plików." + (" Problemy: " + "; ".join(w["bledy"][:3]) if w["bledy"] else "")
        return self.uruchom("przychodzace", f)

    # --- raport diagnostyczny ----------------------------------------------------
    def raport_diagnostyczny(self) -> str:
        w = ["=== Raport Katalogatora ===", f"Wersja: {__version__}"]
        w += [f"{k}: {v}" for k, v in logi.system().items()]
        w += [f"Katalog danych: {self.katalog}", f"Dziennik błędów: {logi.plik()}", "",
              "=== Projekt ===", f"Nazwa: {self.projekt.get('nazwa')} ({self.pid})",
              "Źródła: " + "; ".join(f"{z['sciezka']} [{z['tryb']}]" for z in self.ustawienia["zrodla"]),
              f"Miejsce docelowe: {self.ustawienia['cel']}",
              "Foldery przychodzące: " + "; ".join(self.projekt.get("przychodzace") or []),
              f"Harmonogram: {self.projekt.get('harmonogram') or 'wyłączony'}", ""]
        try:
            st = self.stan()
            w.append("=== Stan ===")
            for k in ("skan", "dup"):
                w.append(f"{k}: {st[k].get('komunikat')} {st[k].get('blad')}")
            for k, z in st["zad"].items():
                if z.get("komunikat") or z.get("blad"):
                    w.append(f"{k}: {z.get('komunikat')} {z.get('blad')}")
            for k in ("plan", "analiza", "duplikaty", "przychodzace"):
                if st.get(k):
                    krotko = {a: b for a, b in st[k].items() if not isinstance(b, (list, dict))}
                    w.append(f"{k}: {krotko}")
            db = self.db()
            try:
                w.append("Pliki wg rodzaju: " + ", ".join(
                    f"{r[0]} {r[1]}" for r in db.execute("SELECT rodzaj, COUNT(*) FROM pliki GROUP BY rodzaj")))
                bledy = db.execute("SELECT wzgledna, blad FROM pliki WHERE blad IS NOT NULL LIMIT 15").fetchall()
                n_bledow = db.execute("SELECT COUNT(*) FROM pliki WHERE blad IS NOT NULL").fetchone()[0]
                if n_bledow:
                    w += ["", f"=== Pliki z nieczytelnymi metadanymi ({n_bledow}) ==="]
                    w += [f"{r[0]}: {r[1]}" for r in bledy]
                bl_wyk = db.execute("SELECT sciezka, wynik FROM plan WHERE wynik LIKE 'blad%' LIMIT 15").fetchall()
                if bl_wyk:
                    w += ["", "=== Błędy porządkowania ==="] + [f"{r[0]}: {r[1]}" for r in bl_wyk]
                w += ["", "=== Dziennik prac (ostatnie) ==="]
                w += [time.strftime("%Y-%m-%d %H:%M", time.localtime(x["czas"])) + f"  [{x['typ']}] {x['opis']}"
                      for x in projekty.dziennik(db, 20)]
            finally:
                db.close()
        except Exception as e:
            w.append(f"(nie udało się zebrać stanu: {type(e).__name__}: {e})")
        w += ["", "=== Dziennik błędów (ostatnie linie) ===", logi.ogon(300) or "(pusty)"]
        return "\n".join(w)

    def zapisz_raport(self, opis: str = "") -> Path:
        folder = next((p for p in (Path.home() / "Downloads", Path.home() / "Pobrane", Path.home() / "Desktop")
                       if p.is_dir()), self.katalog)
        plik = folder / f"Katalogator-raport-{time.strftime('%Y%m%d-%H%M%S')}.txt"
        tekst = self.raport_diagnostyczny()
        if opis.strip():
            tekst = "=== Opis problemu ===\n" + opis.strip() + "\n\n" + tekst
        plik.write_text(tekst, encoding="utf-8")
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(plik)])
        LOG.info("Zapisano raport diagnostyczny: %s", plik)
        return plik

    def url_zgloszenia(self, opis_uzytkownika: str = "") -> str:
        from urllib.parse import quote
        bledy = [l for l in logi.ogon(400).splitlines() if " ERROR " in l or " CRITICAL" in l or "Traceback" in l
                 or l.startswith(("  ", "\t")) or "Error" in l]
        tresc = (f"**Opis problemu:**\n{opis_uzytkownika or '(opisz, co robiłeś i co poszło nie tak)'}\n\n"
                 f"**Wersja:** {__version__}\n**System:** {logi.system()['system']}\n\n"
                 "**Ostatnie błędy z dziennika:**\n```\n" + "\n".join(bledy[-60:])[-4500:] + "\n```\n\n"
                 "_Pełny raport zapisz przyciskiem „Zapisz plik” w programie i dołącz tutaj (przeciągnij plik)._")
        tytul = "Problem: " + (opis_uzytkownika.splitlines()[0][:80] if opis_uzytkownika else "Katalogator " + __version__)
        return (f"https://github.com/{aktualizacje.REPO}/issues/new?title={quote(tytul)}&body={quote(tresc)}"
                )[:7800]

    def zainstaluj_aktualizacje(self, url: str, zamknij) -> str | None:
        def f(db, postep, przerwij):
            aktualizacje.pobierz_i_uruchom(url, postep=postep, przerwij=przerwij)
            threading.Timer(3, zamknij).start()  # zwolnij plik programu dla instalatora
            return "Uruchomiono instalator nowej wersji — Katalogator zaraz się zamknie."
        return self.uruchom("aktualizacja", f)

    def z_db(self, funkcja, *a, **kw):
        db = self.db()
        try:
            return funkcja(db, *a, **kw)
        finally:
            db.close()

    def raport_html(self) -> str:
        db = skaner.otworz_baze(self.baza)
        try:
            return raport.html_raport(raport.zbierz(db))
        finally:
            db.close()


def _handler(stan: Stan, token: str, zamknij):
    class H(BaseHTTPRequestHandler):
        server_version = "Katalogator"

        def log_message(self, *a):  # bez wypisywania do konsoli (aplikacja okienkowa)
            pass

        def _ok_token(self, q) -> bool:
            return secrets.compare_digest(self.headers.get("X-Token") or q.get("t", [""])[0], token)

        def _wyslij(self, tresc, typ="application/json; charset=utf-8", kod=HTTPStatus.OK):
            if not isinstance(tresc, (bytes, str)):
                tresc = json.dumps(tresc, ensure_ascii=False)
            dane = tresc.encode("utf-8") if isinstance(tresc, str) else tresc
            if self.command == "POST":
                stan.zmiana()  # po wykonaniu operacji, przed odpowiedzią — odśwież podsumowania
            self.send_response(kod)
            self.send_header("Content-Type", typ)
            self.send_header("Content-Length", str(len(dane)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(dane)

        def _strumien(self, sciezka: str | None):
            """Wysyła film z obsługą zakresów (Range) — przeglądarka czyta tylko potrzebny fragment."""
            if not sciezka or not os.path.isfile(sciezka):
                return self._wyslij(b"", "text/plain", HTTPStatus.NOT_FOUND)
            rozm = os.path.getsize(sciezka)
            typ = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/mp4", ".3gp": "video/3gpp",
                   ".webm": "video/webm", ".mkv": "video/webm"}.get(Path(sciezka).suffix.lower(),
                                                                   "application/octet-stream")
            start, koniec = 0, rozm - 1
            zakres = self.headers.get("Range", "")
            m = __import__("re").match(r"bytes=(\d*)-(\d*)", zakres)
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    koniec = min(int(m.group(2)) if m.group(2) else rozm - 1, rozm - 1)
                else:
                    start = max(0, rozm - int(m.group(2)))
                if start > koniec:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{rozm}")
                    self.end_headers()
                    return None
                self.send_response(HTTPStatus.PARTIAL_CONTENT)
                self.send_header("Content-Range", f"bytes {start}-{koniec}/{rozm}")
            else:
                self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", typ)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(koniec - start + 1))
            self.end_headers()
            try:
                with open(sciezka, "rb") as f:
                    f.seek(start)
                    zostalo = koniec - start + 1
                    while zostalo > 0:
                        k = f.read(min(1 << 20, zostalo))
                        if not k:
                            break
                        self.wfile.write(k)
                        zostalo -= len(k)
            except (ConnectionError, OSError):
                pass  # przeglądarka przerwała pobieranie (np. przewinięcie) — to normalne
            return None

        def _json(self) -> dict:
            dl = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(dl) or b"{}")
            except ValueError:
                return {}

        def do_GET(self):
            self._bezpiecznie(self._get)

        def do_POST(self):
            self._bezpiecznie(self._post)

        def _bezpiecznie(self, f):
            try:
                f()
            except (ConnectionError, BrokenPipeError):
                pass
            except Exception as e:
                LOG.exception("Błąd obsługi %s %s", self.command, urlparse(self.path).path)
                try:
                    self._wyslij({"blad": f"Błąd programu: {type(e).__name__}: {e}. Szczegóły zapisano w dzienniku "
                                          f"— użyj „Zgłoś problem”."}, kod=HTTPStatus.INTERNAL_SERVER_ERROR)
                except Exception:
                    pass

        def _get(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path in ("/", "/index.html"):
                if not self._ok_token(q):
                    return self._wyslij("Brak dostępu", "text/plain; charset=utf-8", HTTPStatus.FORBIDDEN)
                html = (UI / "index.html").read_bytes()
                motyw = aktualizacje._ustawienia(stan.katalog).get("motyw", "dark")
                if motyw in ("dark", "light"):  # od razu właściwy motyw — bez mignięcia przy starcie
                    html = html.replace(b'<html lang="pl">', f'<html lang="pl" data-theme="{motyw}">'.encode(), 1)
                return self._wyslij(html, "text/html; charset=utf-8")
            if not u.path.startswith("/ui/") and not self._ok_token(q):
                return self._wyslij({"blad": "brak dostępu"}, kod=HTTPStatus.FORBIDDEN)
            if not u.path.startswith("/ui/"):
                stan.ostatni_ping = time.time()
            if u.path == "/api/ping":
                return self._wyslij({"ok": True, "wersja": __version__, "zajety": stan.zajety()})
            if u.path == "/api/stan":
                return self._wyslij(stan.stan())
            if u.path == "/raport":
                return self._wyslij(stan.raport_html(), "text/html; charset=utf-8")
            if u.path.startswith("/ui/"):
                p = galeria.plik_ui(u.path)  # także podfoldery (mapa/leaflet.js) — nigdy spoza katalogu ui
                return self._wyslij(*p) if p else self._wyslij(b"", "text/plain", HTTPStatus.NOT_FOUND)
            if u.path == "/galeria":
                return self._wyslij((UI / "galeria.html").read_bytes(), "text/html; charset=utf-8")
            if u.path.startswith("/api/g/"):
                w = galeria.obsluz_api(stan.galeria(q.get("z", ["biblioteka"])[0]), u.path, q)
                if w is None:
                    return self._wyslij(b"", "text/plain", HTTPStatus.NOT_FOUND)
                if w[0] == "film":
                    return galeria.wyslij_strumien(self, w[1])
                if w[0] == "film-mp4":
                    return filmy.wyslij_mp4(self, w[1], w[2], w[3])
                if w[1]:
                    return self._wyslij(w[0], w[1]) if w[0] is not None else \
                        self._wyslij(b"", "text/plain", HTTPStatus.NOT_FOUND)
                return self._wyslij(w[0])
            if u.path == "/api/plan/aktualnosc":
                return self._wyslij(stan.z_db(planista.aktualnosc))
            if u.path == "/api/plan/drzewo":
                return self._wyslij({"foldery": stan.z_db(planista.drzewo),
                                     "podsumowanie": stan.z_db(planista.podsumowanie),
                                     "przejrzane": sorted(stan.z_db(projekty.przejrzane))})
            if u.path == "/api/raport-bledow":
                return self._wyslij({"tekst": stan.raport_diagnostyczny(), "plik_logu": str(logi.plik() or "")})
            if u.path == "/api/aktualizacja":
                return self._wyslij(aktualizacje.sprawdz(stan.katalog, wymus=q.get("wymus", ["0"])[0] == "1"))
            if u.path == "/api/o-programie":
                return self._wyslij({"wersja": __version__, "katalog": str(stan.katalog),
                                     "plik_logu": str(logi.plik() or ""), **logi.system(),
                                     "sprawdzaj_aktualizacje": aktualizacje.wlaczone(stan.katalog)})
            if u.path == "/api/projekty":
                return self._wyslij({"projekty": stan.projekty.lista(), "biezacy": stan.pid})
            if u.path == "/api/projekt/dziennik":
                return self._wyslij({"wpisy": stan.z_db(projekty.dziennik, 60)})
            if u.path == "/api/plan/pliki":
                return self._wyslij(stan.z_db(planista.pliki_folderu, q.get("folder", [""])[0],
                                              _int(q, "od", 0), min(_int(q, "ile", 200), 500)))
            if u.path == "/api/plan/szukaj":
                return self._wyslij(stan.z_db(planista.szukaj, q.get("q", [""])[0], q.get("filtr", [""])[0],
                                              _int(q, "od", 0), min(_int(q, "ile", 200), 500)))
            if u.path == "/api/plan/sprawdz":
                return self._wyslij(stan.z_db(wykonawca.sprawdz))
            if u.path == "/api/nie-z-aparatu":
                pliki = stan.z_db(duplikaty.zwin_kopie, stan.z_db(kategorie.do_sprawdzenia))  # kopie = 1 karta
                stan.przygotuj_miniatury([p["id"] for p in pliki[:400]], srednia=True)
                return self._wyslij({"pliki": pliki})
            if u.path == "/api/dokumenty":
                kand = stan.z_db(duplikaty.zwin_kopie, stan.z_db(analiza.kandydaci_dokumentow))  # kopie = 1 karta
                kat = stan.z_db(kategorie.kategorie_plikow, [k["id"] for k in kand])
                for k in kand:
                    k["kat"] = kat.get(k["id"])
                stan.przygotuj_miniatury([k["id"] for k in kand[:400]], srednia=True)
                return self._wyslij({"kandydaci": kand})
            if u.path == "/api/podobne":
                przejrz = stan.z_db(duplikaty.przejrzane_klucze, "podobne")
                grupy = [g for g in stan.z_db(analiza.grupy_podobnych)
                         if "|".join(sorted(w["sciezka"] for w in g)) not in przejrz]
                od, ile = _int(q, "od", 0), min(_int(q, "ile", 30), 200)
                wycinek = grupy[od:od + ile]
                kat = stan.z_db(kategorie.kategorie_plikow, [w["id"] for g in wycinek for w in g])
                odc = stan.z_db(duplikaty.odciski_wg_id, [w["id"] for g in wycinek for w in g])
                # ta strona i następna — w tle, zanim okno o nie poprosi
                stan.przygotuj_miniatury([w["id"] for g in grupy[od:od + 2 * ile] for w in g], srednia=True)
                return self._wyslij({"razem": len(grupy), "przejrzane": len(przejrz),
                                     "ile_kopii": sum(w.get("kopia", False) for g in grupy for w in g),
                                     "ile_reszty": sum(len(g) - 1 for g in grupy), "grupy": [
                    [{**{k: w[k] for k in ("id", "sciezka", "wzgledna", "mtime", "rozmiar", "szer", "wys", "ostrosc")},
                      "kat": kat.get(w["id"]),
                      # identyczna kopia innego zdjęcia z tej grupy (ten sam odcisk zawartości)
                      "kopia": bool(w.get("kopia")) or bool(odc.get(w["id"]) and any(odc.get(x["id"]) == odc[w["id"]]
                                                                                   for x in g[:i]))}
                     for i, w in enumerate(g)] for g in wycinek]})
            if u.path == "/api/smieci":
                return self._wyslij({"pliki": stan.z_db(sprzatanie.lista_smieci)})
            if u.path == "/api/odlozone":
                w = sprzatanie.odlozone(stan.korzenie_kosza())
                cel = stan.kosz_w_celu()
                if cel:  # kosz ma być jeden — w miejscu docelowym; ile jeszcze leży w źródłach
                    w["docelowy"] = os.path.join(cel, duplikaty.FOLDER_ODLOZONE)
                    w["poza_celem"] = sum(1 for k in w["kategorie"] for f in k["foldery"]
                                          if not dyski.zawiera(cel, f))
                return self._wyslij(w)
            if u.path == "/api/nieostre":
                pliki = stan.z_db(analiza.najmniej_ostre, min(_int(q, "ile", 120), 500))
                stan.przygotuj_miniatury([p["id"] for p in pliki])
                return self._wyslij({"pliki": pliki})
            if u.path == "/api/przegladarka":
                return self._wyslij({**stan.przegladarka.opis(), "katalogator_pracuje": stan.zajety()})
            if u.path == "/api/dyski":
                return self._wyslij({"dyski": dyski.lista_dyskow()})
            if u.path == "/api/foldery":
                return self._wyslij(dyski.podfoldery(q.get("sciezka", [""])[0]))
            if u.path == "/api/duplikaty":
                try:
                    od, ile = int(q.get("od", ["0"])[0]), min(int(q.get("ile", ["100"])[0]), 200)
                except ValueError:
                    od, ile = 0, 100
                w = stan.grupy(q.get("rodzaj", [""])[0], od, ile)
                stan.przygotuj_miniatury([g["pliki"][0]["id"] for g in w["grupy"] if g["rodzaj"] == "zdjecie"])
                return self._wyslij(w)
            if u.path == "/plik":
                return self._strumien(stan.sciezka_filmu(_int(q, "id", 0)))
            if u.path == "/film-mp4":  # stary / nieznany przeglądarce format — przerabiany w locie
                return filmy.wyslij_mp4(self, stan.sciezka_filmu(_int(q, "id", 0)), max(0, _int(q, "od", 0)),
                                        q.get("f", [""])[0] == "webm")
            if u.path == "/miniatura-filmu":
                jpeg = stan.miniatura_filmu(_int(q, "id", 0))
                return self._wyslij(jpeg, "image/jpeg") if jpeg else self._wyslij(b"", "text/plain", HTTPStatus.NOT_FOUND)
            if u.path == "/miniatura":
                try:
                    id_ = int(q.get("id", ["0"])[0])
                    dane = stan.podglad(id_) if q.get("duza") else stan.miniatura(id_, bool(q.get("srednia")))
                except ValueError:
                    dane = None
                if dane is None:
                    return self._wyslij(b"", "image/jpeg", HTTPStatus.NOT_FOUND)
                return self._wyslij(dane, "image/jpeg")
            self._wyslij({"blad": "nie ma"}, kod=HTTPStatus.NOT_FOUND)

        def _post(self):
            u = urlparse(self.path)
            if not self._ok_token(parse_qs(u.query)):
                return self._wyslij({"blad": "brak dostępu"}, kod=HTTPStatus.FORBIDDEN)
            stan.ostatni_ping = time.time()
            dane = self._json()
            if u.path.startswith("/api/g/"):  # ulubione, albumy, miniatury filmów — dane galerii, nie projektu
                z = parse_qs(u.query).get("z", ["biblioteka"])[0]
                usuwa = u.path in galeria.ZMIANY_PLIKOW
                if usuwa and z != "przegladarka" and stan.zajety():
                    return self._wyslij({"blad": "Poczekaj, aż skończy się bieżące zadanie."}, kod=HTTPStatus.CONFLICT)
                w = galeria.obsluz_post(stan.galeria(z), u.path, dane)
                if w is None:
                    return self._wyslij({"blad": "nie ma"}, kod=HTTPStatus.NOT_FOUND)
                if u.path == "/api/g/lokalizacja" and w.get("sciezki"):
                    stan.rozeslij_lokalizacje(z, w)
                if usuwa and z != "przegladarka":
                    with stan.blokada:
                        stan.wersja_danych += 1
                    stan.przegladarka.zglos_zmiany()
                return self._wyslij(w, kod=HTTPStatus.BAD_REQUEST if "blad" in w else HTTPStatus.OK)
            if u.path == "/api/przegladarka/auto":
                return self._wyslij(stan.przegladarka.ustaw_auto(bool(dane.get("auto")), dane.get("co_godzin")))
            stan.zmiana()
            if u.path == "/api/ustawienia":
                stan.zapisz_ustawienia(dane)
                zmiana = None
                if stan.ma_wyniki() and not stan.zajety():  # Kopiuj ↔ Przenieś: od razu w istniejącej propozycji
                    zmiana = stan.z_db(planista.zmien_tryb, stan.ustawienia["zrodla"])
                    if zmiana["zmienione"]:
                        with stan.blokada:
                            stan.wersja_danych += 1
                w = stan.stan()
                if zmiana:
                    w["zmiana_trybu"] = zmiana
                return self._wyslij(w)
            if u.path == "/api/nowy-folder":
                w = dyski.nowy_folder(str(dane.get("w", "")), str(dane.get("nazwa", "")))
                return self._wyslij(w, kod=HTTPStatus.BAD_REQUEST if "blad" in w else HTTPStatus.OK)
            if u.path == "/api/autostart":
                blad = ustaw_autostart(bool(dane.get("wlacz")))
                return self._wyslij({"blad": blad} if blad else {"autostart": autostart()},
                                    kod=HTTPStatus.BAD_REQUEST if blad else HTTPStatus.OK)
            if u.path == "/api/telefon":
                return self._wyslij(stan.telefon(bool(dane.get("wlacz")), str(dane.get("zakres") or "biblioteka"),
                                                bool(dane.get("sterowanie", True)),
                                                str(dane["pin"]) if "pin" in dane else None))
            if u.path == "/api/skanuj":
                blad = stan.rozpocznij_skan()
                return self._wyslij({"blad": blad} if blad else stan.stan(),
                                    kod=HTTPStatus.BAD_REQUEST if blad else HTTPStatus.OK)
            if u.path == "/api/duplikaty/szukaj":
                blad = stan.szukaj_duplikatow()
                return self._wyslij({"blad": blad} if blad else stan.stan(),
                                    kod=HTTPStatus.BAD_REQUEST if blad else HTTPStatus.OK)
            if u.path == "/api/duplikaty/przenies":
                w = stan.przenies_duplikaty(dane.get("decyzje") or [])
                return self._wyslij(w, kod=HTTPStatus.BAD_REQUEST if "blad" in w else HTTPStatus.OK)
            if u.path == "/api/duplikaty/cofnij":
                w = stan.cofnij()
                return self._wyslij(w, kod=HTTPStatus.BAD_REQUEST if "blad" in w else HTTPStatus.OK)
            proste = {
                "/api/analiza/start": lambda: stan.analizuj(),
                "/api/plan/generuj": lambda: stan.generuj_plan(),
                "/api/wykonaj": lambda: stan.wykonaj(bool(dane.get("usun_puste", True)),
                                                     bool(dane.get("usun_oryginaly", True))),
                "/api/wykonanie/cofnij": lambda: stan.cofnij_wykonanie(),
            }
            if u.path in proste:
                blad = proste[u.path]()
                return self._wyslij({"blad": blad} if blad else stan.stan(),
                                    kod=HTTPStatus.BAD_REQUEST if blad else HTTPStatus.OK)
            if u.path == "/api/tryb":
                blad = stan.przelacz_tryb(str(dane.get("tryb", "")))
                stan._ustaw_kosz()
                return self._wyslij({"blad": blad} if blad else stan.stan(),
                                    kod=HTTPStatus.BAD_REQUEST if blad else HTTPStatus.OK)
            if u.path == "/api/odlozone/do-celu":  # Odłożone ze źródeł → jeden kosz w miejscu docelowym
                blad = stan.przenies_kosz()
                return self._wyslij({"blad": blad} if blad else stan.stan(),
                                    kod=HTTPStatus.BAD_REQUEST if blad else HTTPStatus.OK)
            if u.path == "/api/odlozone/usun" and dane.get("partia"):  # tylko ta jedna operacja odłożenia
                blad = stan.usun_partie(int(dane["partia"]))
                return self._wyslij({"blad": blad} if blad else stan.stan(),
                                    kod=HTTPStatus.BAD_REQUEST if blad else HTTPStatus.OK)
            if u.path == "/api/odlozone/usun":
                kat = dane.get("kategorie")
                blad = stan.usun_odlozone([str(k) for k in kat] if isinstance(kat, list) else None,
                                          bool(dane.get("puste", True)))
                return self._wyslij({"blad": blad} if blad else stan.stan(),
                                    kod=HTTPStatus.BAD_REQUEST if blad else HTTPStatus.OK)
            if u.path == "/api/projekty/nowy":
                pid = stan.projekty.nowy(str(dane.get("nazwa", "")),
                                         {"typ": "sprzatanie" if dane.get("typ") == "sprzatanie" else "porzadkowanie"})
                blad = stan.otworz_projekt(pid)
                return self._wyslij({"blad": blad} if blad else stan.stan(),
                                    kod=HTTPStatus.BAD_REQUEST if blad else HTTPStatus.OK)
            if u.path == "/api/projekty/otworz":
                blad = stan.otworz_projekt(str(dane.get("id", "")))
                return self._wyslij({"blad": blad} if blad else stan.stan(),
                                    kod=HTTPStatus.BAD_REQUEST if blad else HTTPStatus.OK)
            if u.path in ("/api/przychodzace/sprawdz", "/api/przychodzace/wykonaj", "/api/przychodzace/cofnij"):
                blad = stan.przychodzace_zadanie(u.path.rsplit("/", 1)[1])
                return self._wyslij({"blad": blad} if blad else stan.stan(),
                                    kod=HTTPStatus.BAD_REQUEST if blad else HTTPStatus.OK)
            if u.path == "/api/przychodzace/harmonogram":
                try:
                    w = przychodzace.ustaw_harmonogram(stan.projekty, stan.pid, str(dane.get("godzina", "")))
                    stan.projekt = stan.projekty.wczytaj(stan.pid)
                    return self._wyslij(w)
                except ValueError as e:
                    return self._wyslij({"blad": str(e)}, kod=HTTPStatus.BAD_REQUEST)
            if u.path == "/api/log":
                LOG.warning("Okno programu: %s", str(dane.get("tekst", ""))[:2000])
                return self._wyslij({"ok": True})
            if u.path == "/api/raport-bledow/zapisz":
                return self._wyslij({"plik": str(stan.zapisz_raport(str(dane.get("opis", ""))[:5000]))})
            if u.path == "/api/raport-bledow/github":
                url_z = stan.url_zgloszenia(str(dane.get("opis", ""))[:1500])
                webbrowser.open(url_z)
                return self._wyslij({"url": url_z})
            if u.path == "/api/otworz-strone":
                adres = str(dane.get("url", ""))
                if adres.startswith("https://github.com/"):
                    webbrowser.open(adres)
                return self._wyslij({"ok": True})
            if u.path == "/api/program/ustawienia":
                zmiany = {k: bool(dane[k]) for k in ("sprawdzaj_aktualizacje", "powitanie_widziane") if k in dane}
                if dane.get("motyw") in ("dark", "light", "auto"):
                    zmiany["motyw"] = dane["motyw"]
                return self._wyslij(aktualizacje.zapisz_ustawienia(stan.katalog, **zmiany))
            if u.path == "/api/aktualizacja/instaluj":
                blad = stan.zainstaluj_aktualizacje(str(dane.get("url", "")), zamknij)
                return self._wyslij({"blad": blad} if blad else {"ok": True},
                                    kod=HTTPStatus.BAD_REQUEST if blad else HTTPStatus.OK)
            if u.path == "/api/projekty/zmien":
                w = stan.zmien_projekt(dane)
                return self._wyslij(w, kod=HTTPStatus.BAD_REQUEST if "blad" in w else HTTPStatus.OK)
            if u.path == "/api/projekty/usun":
                blad = stan.usun_projekt(str(dane.get("id", "")))
                return self._wyslij({"blad": blad} if blad else stan.stan(),
                                    kod=HTTPStatus.BAD_REQUEST if blad else HTTPStatus.OK)
            edycja = {
                "/api/plan/przejrzany": lambda db: projekty.oznacz_przejrzany(
                    db, str(dane.get("folder", "")), bool(dane.get("wartosc", True))),
                "/api/plan/zmien-nazwe": lambda db: planista.zmien_nazwe_folderu(db, str(dane.get("stara", "")),
                                                                                   str(dane.get("nowa", ""))),
                "/api/plan/przenies": lambda db: planista.przenies_pliki(db, [int(i) for i in dane.get("ids") or []],
                                                                         str(dane.get("folder", ""))),
                "/api/plan/wyklucz": lambda db: planista.wyklucz(
                    db, [int(i) for i in dane.get("ids") or []] if "ids" in dane else None,
                    dane.get("folder"), bool(dane.get("wartosc", True))),
                "/api/plan/ustaw-miejsce": lambda db: planista.ustaw_miejsce(
                    db, [int(i) for i in dane.get("ids") or []], str(dane.get("miejsce", ""))),
                "/api/plan/ustaw-date": lambda db: planista.ustaw_date(
                    db, [int(i) for i in dane.get("ids") or []], str(dane.get("data", ""))),
                "/api/plan/cofnij": planista.cofnij,
                "/api/plan/ponow": planista.ponow,
                "/api/dokumenty/zapisz": lambda db: {
                    **analiza.zapisz_decyzje(db, [int(i) for i in dane.get("tak") or []],
                                             [int(i) for i in dane.get("nie") or []]),
                    "plan": planista.zastosuj_kategorie(db)},
                "/api/kategoria": lambda db: {  # jedno kliknięcie w Duplikatach / Dokumentach / Podobnych
                    **kategorie.zapisz(db, {int(i): str(dane.get("kat") or "") for i in dane.get("ids") or []}),
                    "plan": planista.zastosuj_kategorie(db)},
                "/api/nie-z-aparatu/zapisz": lambda db: {
                    **kategorie.zapisz(db, {int(k): str(v) for k, v in (dane.get("wybor") or {}).items()}),
                    "plan": planista.zastosuj_kategorie(db)},
                # ⚡ Podobne hurtem: „kopie” — tylko kopie tych samych zdjęć; „najlepsze” — w każdej grupie zostaje ★
                "/api/podobne/auto": lambda db: duplikaty.odloz(db, _podobne_hurtem(db, dane.get("tryb")), "podobne"),
                "/api/odloz": lambda db: duplikaty.odloz(db, [int(i) for i in dane.get("ids") or []],
                                                         dane.get("typ") if dane.get("typ") in ("podobne", "smieci")
                                                         else "nieostre"),
            }
            if u.path in edycja:
                if u.path in ("/api/odloz", "/api/podobne/auto") and stan.zajety():
                    return self._wyslij({"blad": "Poczekaj, aż skończy się bieżące zadanie."}, kod=HTTPStatus.BAD_REQUEST)
                w = stan.z_db(edycja[u.path])
                if u.path in ("/api/odloz", "/api/podobne/auto"):
                    stan.przegladarka.zglos_zmiany()
                return self._wyslij(w, kod=HTTPStatus.BAD_REQUEST if "blad" in w else HTTPStatus.OK)
            if u.path == "/api/przejrzane":  # „zostaw wszystkie” — grupa znika z Duplikatów / Podobnych
                rodzaj = "podobne" if dane.get("rodzaj") == "podobne" else "dup"
                w = stan.z_db(duplikaty.oznacz_przejrzane, rodzaj, [str(k) for k in dane.get("klucze") or []],
                              bool(dane.get("wartosc", True)))
                with stan.blokada:
                    stan.wersja_danych += 1
                return self._wyslij(w)
            if u.path in ("/api/usun", "/api/usun/cofnij"):  # 🗑 w zakładkach projektu
                if stan.zajety():
                    return self._wyslij({"blad": "Poczekaj, aż skończy się bieżące zadanie."}, kod=HTTPStatus.CONFLICT)
                if u.path == "/api/usun":
                    w = stan.z_db(lambda db: usuwanie.usun(db, [int(i) for i in dane.get("ids") or []]))
                else:
                    w = stan.z_db(lambda db: usuwanie.cofnij(db, int(dane.get("partia") or 0)))
                with stan.blokada:
                    stan.wersja_danych += 1
                stan.przegladarka.zglos_zmiany()
                return self._wyslij(w, kod=HTTPStatus.BAD_REQUEST if "blad" in w else HTTPStatus.OK)
            if u.path == "/api/przegladarka/foldery":
                stan.przegladarka.ustaw_foldery([str(f) for f in dane.get("foldery") or []])
                return self._wyslij(stan.przegladarka.opis())
            if u.path == "/api/przegladarka/zestaw":
                w = stan.przegladarka.zestaw(str(dane.get("akcja", "")), int(dane.get("id") or 0) or None,
                                             str(dane.get("nazwa", "")))
                return self._wyslij(w, kod=HTTPStatus.BAD_REQUEST if w.get("blad") and "zestawy" not in w
                                    else HTTPStatus.OK)
            if u.path == "/api/przegladarka/skanuj":
                blad = stan.przegladarka.skanuj()
                return self._wyslij({"blad": blad} if blad else stan.przegladarka.opis(),
                                    kod=HTTPStatus.BAD_REQUEST if blad else HTTPStatus.OK)
            if u.path == "/api/przegladarka/przerwij":
                stan.przegladarka.przerwij.set()
                return self._wyslij({"ok": True})
            if u.path == "/api/przerwij":
                stan.przerwij.set()
                return self._wyslij({"ok": True})
            if u.path == "/api/zamknij":
                self._wyslij({"ok": True})
                stan.przerwij.set()
                threading.Thread(target=zamknij, daemon=True).start()
                return None
            self._wyslij({"blad": "nie ma"}, kod=HTTPStatus.NOT_FOUND)

    return H


# --- uruchamianie razem z Windows (bez okna; okno otwiera skrót Katalogatora) -------------------------------
_KLUCZ_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAZWA_RUN = "Katalogator"


def autostart_mozliwy() -> bool:
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def autostart() -> bool:
    if not autostart_mozliwy():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KLUCZ_RUN) as k:
            winreg.QueryValueEx(k, _NAZWA_RUN)
        return True
    except OSError:
        return False


def ustaw_autostart(wlacz: bool) -> str | None:
    if not autostart_mozliwy():
        return "Uruchamianie z Windows działa tylko w zainstalowanym programie na Windows."
    import winreg
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _KLUCZ_RUN) as k:
            if wlacz:
                winreg.SetValueEx(k, _NAZWA_RUN, 0, winreg.REG_SZ, f'"{sys.executable}" --w-tle')
            else:
                try:
                    winreg.DeleteValue(k, _NAZWA_RUN)
                except FileNotFoundError:
                    pass
    except OSError as e:
        return f"Nie udało się zmienić autostartu: {e}"
    LOG.info("Autostart z Windows: %s", wlacz)
    return None


def _podobne_hurtem(db, tryb) -> list[int]:
    """Pliki do odłożenia ze WSZYSTKICH nieprzejrzanych grup podobnych."""
    przejrz = duplikaty.przejrzane_klucze(db, "podobne")
    ids = []
    for g in analiza.grupy_podobnych(db):
        if "|".join(sorted(w["sciezka"] for w in g)) in przejrz:
            continue
        ids += [w["id"] for w in (g[1:] if tryb == "najlepsze" else g) if tryb == "najlepsze" or w.get("kopia")]
    return ids


def _int(q: dict, klucz: str, domyslnie: int) -> int:
    try:
        return int(q.get(klucz, [domyslnie])[0])
    except (TypeError, ValueError):
        return domyslnie


def uruchom_serwer(katalog: Path | None = None, port: int = 0):
    """Zwraca (serwer, adres_url, stan). Serwer trzeba obsłużyć: serve_forever()."""
    stan = Stan(katalog or katalog_danych())
    token = secrets.token_urlsafe(24)
    serwer: ThreadingHTTPServer | None = None

    def zamknij():
        if serwer is not None:
            serwer.shutdown()

    serwer = ThreadingHTTPServer(("127.0.0.1", port), _handler(stan, token, zamknij))
    serwer.daemon_threads = True
    stan.glowny = (serwer.server_address[1], token)  # dla „pełnego programu z telefonu” (przez serwer telefonu)
    url = f"http://127.0.0.1:{serwer.server_address[1]}/?t={token}"
    return serwer, url, stan


def otworz_okno(url: str) -> None:
    """Edge/Chrome w trybie aplikacji (okno bez paska adresu), inaczej domyślna przeglądarka."""
    kandydaci = []
    if sys.platform == "win32":
        for zm in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
            baza = os.environ.get(zm)
            if baza:
                kandydaci += [Path(baza) / "Microsoft/Edge/Application/msedge.exe",
                              Path(baza) / "Google/Chrome/Application/chrome.exe"]
    else:
        kandydaci += [Path(p) for p in filter(None, (shutil.which("microsoft-edge"),
                                                     shutil.which("google-chrome"),
                                                     shutil.which("chromium")))]
    for exe in kandydaci:
        if exe.exists():
            try:
                subprocess.Popen([str(exe), f"--app={url}", "--start-maximized"])
                return
            except OSError:
                continue
    webbrowser.open(url)


def _dzialajaca_instancja(katalog: Path) -> str | None:
    """Adres okna już działającego Katalogatora (np. po zamknięciu okna w trakcie długiego zadania)."""
    plik = katalog / "instancja.json"
    try:
        url = json.loads(plik.read_text(encoding="utf-8"))["url"]
        baza, token = url.split("/?t=")
        import urllib.request
        with urllib.request.urlopen(f"{baza}/api/ping?t={token}", timeout=3) as r:
            if json.loads(r.read()).get("ok"):
                return url
    except Exception:
        pass
    return None


def main(otworz: bool = True) -> None:
    katalog = katalog_danych()
    logi.konfiguruj(katalog)
    istniejaca = _dzialajaca_instancja(katalog)
    if istniejaca:  # drugi raz nie uruchamiamy — dwa programy na jednej bazie przeszkadzałyby sobie
        LOG.info("Katalogator już działa — otwieram jego okno")
        if otworz:
            otworz_okno(istniejaca)
        return
    LOG.info("Start Katalogatora %s — %s", __version__, logi.system())
    serwer, url, stan = uruchom_serwer(katalog)
    # Przeglądarka: nowe zdjęcia z dysków same się dopisują — ale nie w trakcie zadań Katalogatora (ten sam dysk)
    stan.przegladarka.uruchom_auto(zajety=stan.zajety)
    plik_instancji = katalog / "instancja.json"
    try:
        plik_instancji.write_text(json.dumps({"url": url, "pid": os.getpid()}), encoding="utf-8")
    except OSError:
        pass

    def pilnuj():  # zamknięcie okna = koniec programu (skan jest wznawialny)
        while True:
            time.sleep(10)
            if time.time() - stan.ostatni_ping > BEZ_PINGU_ZAMKNIJ_PO:
                if stan.zajety() or stan.telefon_wlaczony():
                    continue  # zadanie trwa albo telefon włączony — program działa dalej (bez okna)
                stan.przerwij.set()
                serwer.shutdown()
                return

    threading.Thread(target=pilnuj, daemon=True).start()
    stan.telefon_po_starcie()
    if otworz:
        otworz_okno(url)
    try:
        serwer.serve_forever()
    finally:
        serwer.server_close()
        try:
            if json.loads(plik_instancji.read_text(encoding="utf-8")).get("pid") == os.getpid():
                plik_instancji.unlink()
        except (OSError, ValueError):
            pass


if __name__ == "__main__":
    main()
