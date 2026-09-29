"""Aplikacja okienkowa: lokalny serwer + interfejs HTML w oknie Edge (tryb aplikacji).

Serwer słucha tylko na 127.0.0.1 i wymaga losowego tokenu, więc inne strony
ani komputery w sieci nie mają do niego dostępu.
"""

from __future__ import annotations

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

from . import (__version__, aktualizacje, analiza, duplikaty, dyski, logi, planista, projekty, przychodzace, raport,
               kategorie, skaner, stabilnosc, wykonawca)
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
        pid = self.projekty.ostatni() or self.projekty.nowy("Mój projekt")
        self._otworz(pid)

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
        self.zad = {n: self._pusty() for n in ("analiza", "plan", "wykonanie", "przychodzace", "aktualizacja")}
        self.miniatury: dict[int, bytes] = {}
        self.projekty.ustaw_ostatni(pid)
        self.wersja_danych += 1

    def otworz_projekt(self, pid: str) -> str | None:
        if self.zajety():
            return "Poczekaj, aż skończy się bieżące zadanie."
        try:
            self._otworz(pid)
        except ValueError as e:
            return str(e)
        return None

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
                                                             "harmonogram")},
                "dup": dup, "zad": zad, "ma_wyniki": ma, "duplikaty": None, "do_cofniecia": None,
                "analiza": None, "plan": None, "wykonanie": None, "przychodzace": None}
        dane["biezace"] = self._biezace(skan, dup, zad)
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
                    except Exception:
                        LOG.exception("Nie udało się policzyć podsumowań")
                    finally:
                        self._licze_podsumowania.release()
                w = threading.Thread(target=licz, daemon=True)
                w.start()
                w.join(1.5)
                if not w.is_alive():
                    cache = wynik
            dane["wczytuje"] = self._licze_podsumowania.locked() and w_cache < 0
            dane.update(cache)
        return dane

    def _przelicz_podsumowania(self, wersja: int) -> dict:
        cache = {}
        db = self.db()
        try:
            if db.execute("SELECT 1 FROM odciski LIMIT 1").fetchone():
                cache["duplikaty"] = duplikaty.podsumowanie(db)
            cache["do_cofniecia"] = duplikaty.ostatnia_partia(db)
            if db.execute("SELECT 1 FROM analiza LIMIT 1").fetchone():
                cache["analiza"] = analiza.podsumowanie(db)
            if planista.istnieje(db):
                cache["plan"] = planista.podsumowanie(db)
            cache["nie_z_aparatu"] = sum(1 for p in kategorie.do_sprawdzenia(db) if not p["decyzja"])
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
                   "przychodzace": "Folder przychodzący", "aktualizacja": "Aktualizacja"}

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

        threading.Thread(target=praca, daemon=True).start()
        return None

    # --- skan w tle ----------------------------------------------------
    def rozpocznij_skan(self) -> str | None:
        foldery = [z["sciezka"] for z in self.ustawienia["zrodla"]]
        cel = self.ustawienia["cel"]
        if cel and not any(dyski.zawiera(z, cel) for z in foldery):
            foldery.append(cel)  # miejsce docelowe też skanujemy (o ile nie leży w źródle)
        if not foldery:
            return "Najpierw wybierz folder do uporządkowania."
        brak = [f for f in foldery if not os.path.isdir(f)]
        if brak:
            return "Nie mogę otworzyć folderu: " + ", ".join(brak)
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
            komunikat, blad = f"Gotowe — przejrzano {razem} plików.", ""
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
            komunikat, blad = (f"Znaleziono {w['nadmiar']} zbędnych kopii "
                               f"({raport.rozmiar_txt(w['bajty'])})." if w["nadmiar"]
                               else "Nie znaleziono duplikatów."), ""
        except skaner.Przerwano:
            komunikat, blad = "Przerwano. Sprawdzone pliki są zapamiętane.", ""
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
            return {"grupy": grupy, "podsumowanie": duplikaty.podsumowanie(db)}
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

    def cofnij(self) -> dict:
        if self.zajety():
            return {"blad": "Poczekaj, aż skończy się bieżące zadanie."}
        db = self.db()
        try:
            return duplikaty.cofnij(db)
        finally:
            db.close()

    def miniatura(self, id_: int, srednia: bool = False) -> bytes | None:
        klucz = ("s", id_) if srednia else id_
        if klucz in self.miniatury:
            return self.miniatury[klucz]
        db = self.db()
        try:
            r = db.execute("SELECT sciezka FROM pliki WHERE rowid=? AND rodzaj='zdjecie'", (id_,)).fetchone()
            if not r:  # plik z planu, którego nie ma już w skanie (np. w miejscu docelowym)
                r = db.execute("SELECT sciezka FROM plan WHERE plik_id=? AND rodzaj='zdjecie'", (id_,)).fetchone()
        finally:
            db.close()
        if not r:
            return None
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
        except Exception:
            return None
        if len(self.miniatury) > 600:
            self.miniatury.clear()
        self.miniatury[klucz] = buf.getvalue()
        return self.miniatury[klucz]

    def sciezka_filmu(self, id_: int) -> str | None:
        db = self.db()
        try:
            r = db.execute("SELECT sciezka FROM pliki WHERE rowid=? AND rodzaj='film'", (id_,)).fetchone() or \
                db.execute("SELECT sciezka FROM plan WHERE plik_id=? AND rodzaj='film'", (id_,)).fetchone()
        finally:
            db.close()
        return r["sciezka"] if r else None

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

    def wykonaj(self, usun_puste: bool) -> str | None:
        def f(db, postep, przerwij):
            w = wykonawca.wykonaj(db, postep=postep, przerwij=przerwij, usun_puste=usun_puste)
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
                return self._wyslij((UI / "index.html").read_bytes(), "text/html; charset=utf-8")
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
            if u.path.startswith("/ui/") and u.path.endswith((".js", ".css", ".png", ".ico")):
                plik = UI / os.path.basename(u.path)
                if plik.is_file():
                    typ = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                           ".png": "image/png", ".ico": "image/x-icon"}[plik.suffix]
                    return self._wyslij(plik.read_bytes(), typ)
                return self._wyslij(b"", "text/plain", HTTPStatus.NOT_FOUND)
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
                return self._wyslij({"pliki": stan.z_db(kategorie.do_sprawdzenia)})
            if u.path == "/api/dokumenty":
                kand = stan.z_db(analiza.kandydaci_dokumentow)
                kat = stan.z_db(kategorie.kategorie_plikow, [k["id"] for k in kand])
                for k in kand:
                    k["kat"] = kat.get(k["id"])
                return self._wyslij({"kandydaci": kand})
            if u.path == "/api/podobne":
                grupy = stan.z_db(analiza.grupy_podobnych)
                od, ile = _int(q, "od", 0), min(_int(q, "ile", 30), 200)
                wycinek = grupy[od:od + ile]
                kat = stan.z_db(kategorie.kategorie_plikow, [w["id"] for g in wycinek for w in g])
                return self._wyslij({"razem": len(grupy), "grupy": [
                    [{**{k: w[k] for k in ("id", "sciezka", "wzgledna", "mtime", "rozmiar", "szer", "wys", "ostrosc")},
                      "kat": kat.get(w["id"])} for w in g] for g in wycinek]})
            if u.path == "/api/nieostre":
                return self._wyslij({"pliki": stan.z_db(analiza.najmniej_ostre, min(_int(q, "ile", 120), 500))})
            if u.path == "/api/dyski":
                return self._wyslij({"dyski": dyski.lista_dyskow()})
            if u.path == "/api/foldery":
                return self._wyslij(dyski.podfoldery(q.get("sciezka", [""])[0]))
            if u.path == "/api/duplikaty":
                try:
                    od, ile = int(q.get("od", ["0"])[0]), min(int(q.get("ile", ["100"])[0]), 200)
                except ValueError:
                    od, ile = 0, 100
                return self._wyslij(stan.grupy(q.get("rodzaj", [""])[0], od, ile))
            if u.path == "/plik":
                return self._strumien(stan.sciezka_filmu(_int(q, "id", 0)))
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
            stan.zmiana()
            if u.path == "/api/ustawienia":
                stan.zapisz_ustawienia(dane)
                return self._wyslij(stan.stan())
            if u.path == "/api/nowy-folder":
                w = dyski.nowy_folder(str(dane.get("w", "")), str(dane.get("nazwa", "")))
                return self._wyslij(w, kod=HTTPStatus.BAD_REQUEST if "blad" in w else HTTPStatus.OK)
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
                "/api/wykonaj": lambda: stan.wykonaj(bool(dane.get("usun_puste", True))),
                "/api/wykonanie/cofnij": lambda: stan.cofnij_wykonanie(),
            }
            if u.path in proste:
                blad = proste[u.path]()
                return self._wyslij({"blad": blad} if blad else stan.stan(),
                                    kod=HTTPStatus.BAD_REQUEST if blad else HTTPStatus.OK)
            if u.path == "/api/projekty/nowy":
                pid = stan.projekty.nowy(str(dane.get("nazwa", "")))
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
                d = aktualizacje.zapisz_ustawienia(stan.katalog, sprawdzaj_aktualizacje=bool(
                    dane.get("sprawdzaj_aktualizacje", True)))
                return self._wyslij(d)
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
                "/api/odloz": lambda db: duplikaty.odloz(db, [int(i) for i in dane.get("ids") or []],
                                                         "podobne" if dane.get("typ") == "podobne" else "nieostre"),
            }
            if u.path in edycja:
                if u.path == "/api/odloz" and stan.zajety():
                    return self._wyslij({"blad": "Poczekaj, aż skończy się bieżące zadanie."}, kod=HTTPStatus.BAD_REQUEST)
                w = stan.z_db(edycja[u.path])
                return self._wyslij(w, kod=HTTPStatus.BAD_REQUEST if "blad" in w else HTTPStatus.OK)
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
                subprocess.Popen([str(exe), f"--app={url}", "--window-size=1180,860"])
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
    plik_instancji = katalog / "instancja.json"
    try:
        plik_instancji.write_text(json.dumps({"url": url, "pid": os.getpid()}), encoding="utf-8")
    except OSError:
        pass

    def pilnuj():  # zamknięcie okna = koniec programu (skan jest wznawialny)
        while True:
            time.sleep(10)
            if time.time() - stan.ostatni_ping > BEZ_PINGU_ZAMKNIJ_PO:
                if stan.zajety():
                    continue  # okno zamknięte/zawieszone, ale zadanie trwa — kończymy dopiero po nim
                stan.przerwij.set()
                serwer.shutdown()
                return

    threading.Thread(target=pilnuj, daemon=True).start()
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
