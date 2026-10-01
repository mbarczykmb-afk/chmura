"""Pilot na telefon: stan pracy programu na komputerze i uruchamianie kolejnych kroków.

Projekt zakłada się i ustawia (foldery, miejsce docelowe, decyzje) na komputerze — z telefonu widać, co się dzieje,
i można uruchomić następny krok, przerwać zadanie albo przełączyć projekt. Dostęp tylko po PIN-ie
(ten sam serwer co galeria na telefon), a sterowanie można wyłączyć — wtedy telefon tylko ogląda.
"""

from __future__ import annotations

from . import raport, sprzatanie

# kroki w kolejności — (klucz, tytuł, dla trybu)
KROKI = {
    "porzadkowanie": [("skan", "Skanowanie"), ("dup", "Duplikaty"), ("analiza", "Analiza zdjęć"),
                      ("plan", "Propozycja drzewa"), ("wykonanie", "Porządkowanie plików")],
    "sprzatanie": [("skan", "Skanowanie"), ("dup", "Duplikaty"), ("analiza", "Analiza zdjęć"),
                   ("usuwanie", "Usuwanie odłożonych")],
}
# kroki, które zmieniają pliki na dysku — telefon pyta o potwierdzenie
ZMIENIAJACE = {"wykonanie", "usuwanie"}


def _r(b) -> str:
    return raport.rozmiar_txt(b or 0)


class Pilot:
    def __init__(self, stan, sterowanie: bool = True):
        self.stan = stan
        self.sterowanie = sterowanie

    # --- stan ---------------------------------------------------------------
    def status(self) -> dict:
        s = self.stan
        d = s.stan()
        typ = (d["projekt"] or {}).get("typ") or "porzadkowanie"
        kroki = [self._krok(k, t, d) for k, t in KROKI[typ]]
        nast = next((k for k in kroki if k["dostepny"] and not k["zrobiony"]), None)
        if nast:
            nast["nastepny"] = True
        b = d.get("biezace")
        if b:
            b = dict(b)
            if b.get("bajty_razem"):
                b["procent"] = round(100 * min(1, (b.get("bajty") or 0) / b["bajty_razem"]))
            elif b.get("wszystkie"):
                b["procent"] = round(100 * min(1, (b.get("zrobione") or 0) / b["wszystkie"]))
        prz = s.przegladarka.opis()
        return {
            "wersja": d["wersja"], "sterowanie": self.sterowanie,
            "projekt": {"id": s.pid, "nazwa": d["projekt"].get("nazwa"), "typ": typ,
                        "zrodla": [z["sciezka"] for z in d.get("zrodla") or []], "cel": d.get("cel") or ""},
            "projekty": [{"id": p["id"], "nazwa": p.get("nazwa"), "typ": p.get("typ") or "porzadkowanie"}
                         for p in s.projekty.lista()],
            "biezace": b, "kroki": kroki, "ostatnie": self._ostatnie(d),
            "przegladarka": {k: prz.get(k) for k in ("trwa", "etap", "zrobione", "wszystkie", "komunikat", "blad",
                                                     "ostatni_skan")} | {"foldery": len(prz.get("foldery") or [])},
        }

    @staticmethod
    def _ostatnie(d: dict) -> list[dict]:
        """Komunikaty zakończonych zadań (czym się skończyły) — najpierw błędy."""
        wynik = []
        for nazwa, z in [("skan", d["skan"]), ("dup", d["dup"]), *d["zad"].items()]:
            if not z.get("trwa") and (z.get("komunikat") or z.get("blad")):
                wynik.append({"zadanie": nazwa, "komunikat": z.get("komunikat") or "", "blad": z.get("blad") or ""})
        return sorted(wynik, key=lambda w: not w["blad"])

    def _krok(self, klucz: str, tytul: str, d: dict) -> dict:
        ma = d.get("ma_wyniki")
        k = {"klucz": klucz, "tytul": tytul, "zrobiony": False, "dostepny": True, "opis": "",
             "zmienia_pliki": klucz in ZMIENIAJACE}
        if klucz == "skan":
            k["zrobiony"] = bool(ma)
            k["opis"] = f"{d.get('plikow', 0):,} plików".replace(",", " ") if ma else \
                "Foldery: " + (", ".join(z["sciezka"] for z in d.get("zrodla") or []) or "nie wybrano — wybierz na komputerze")
            k["dostepny"] = bool(d.get("zrodla"))
        elif klucz == "dup":
            p = d.get("duplikaty")
            k["dostepny"], k["zrobiony"] = bool(ma), p is not None
            if p:
                k["opis"] = (f"{p['nadmiar']} zbędnych kopii ({_r(p['bajty'])}) — wybór, co zostawić, na komputerze"
                             if p["nadmiar"] else "Brak duplikatów")
        elif klucz == "analiza":
            p = d.get("analiza")
            k["dostepny"], k["zrobiony"] = bool(ma), bool(p and p["przeanalizowane"] >= p["zdjecia"])
            if p:
                k["opis"] = (f"{p['przeanalizowane']} z {p['zdjecia']} zdjęć · dokumenty: {p['dokumenty']} · "
                             f"grupy podobnych: {p['podobne_grupy']}")
        elif klucz == "plan":
            p = d.get("plan")
            k["dostepny"] = bool(ma and d.get("cel"))
            k["zrobiony"] = p is not None
            if not d.get("cel"):
                k["opis"] = "Najpierw wybierz na komputerze miejsce docelowe („Dokąd?”)."
            elif p:
                k["opis"] = f"{p['kopiuj'] + p['przenies']} plików do uporządkowania ({_r(p['kopiuj_b'] + p['przenies_b'])})"
        elif klucz == "wykonanie":
            p = d.get("plan") or {}
            zostalo = (p.get("kopiuj") or 0) + (p.get("przenies") or 0) + (p.get("oryginaly") or 0)
            k["dostepny"] = bool(p) and zostalo > 0
            k["zrobiony"] = bool(p) and not zostalo and bool(p.get("zrobione"))
            if p:
                k["opis"] = (f"Zostało {zostalo} plików · zrobione: {p.get('zrobione', 0)}" +
                             (f" · błędy: {p['bledy']}" if p.get("bledy") else ""))
        elif klucz == "usuwanie":
            o = sprzatanie.odlozone([z["sciezka"] for z in d.get("zrodla") or []])
            k["dostepny"] = bool(o["plikow"])
            k["opis"] = (f"W „Odłożone” czeka {o['plikow']} plików ({_r(o['bajty'])})" if o["plikow"]
                         else "Nic nie czeka w „Odłożone” — odkładasz na komputerze (Duplikaty, Śmieci…)")
        return k

    # --- usuwanie z telefonu (galeria) ----------------------------------------------------------
    def zajety_projekt(self, zakres: str) -> str | None:
        """Pliki projektu nie zmieniają miejsca w trakcie zadania (Przeglądarka ma osobną bazę)."""
        if zakres != "przegladarka" and self.stan.zajety():
            return "Poczekaj, aż komputer skończy bieżące zadanie."
        return None

    def po_usunieciu(self, zakres: str, lokalizacja: dict | None = None) -> None:
        s = self.stan
        if lokalizacja and lokalizacja.get("sciezki"):
            s.rozeslij_lokalizacje(zakres, lokalizacja)
        if zakres == "przegladarka":
            return
        with s.blokada:
            s.wersja_danych += 1
        s.przegladarka.zglos_zmiany()

    # --- sterowanie ---------------------------------------------------------
    def akcja(self, nazwa: str, dane: dict) -> str | None:
        """Uruchamia krok / przerywa / przełącza projekt. Zwraca komunikat błędu albo None."""
        if not self.sterowanie:
            return "Sterowanie z telefonu jest wyłączone — włącz je na komputerze („📱 Na telefon”)."
        s = self.stan
        if nazwa == "przerwij":
            s.przerwij.set()
            return None
        if nazwa == "projekt":
            blad = s.otworz_projekt(str(dane.get("id", "")))
            if not blad:
                s.projekty.ustaw_ostatni(s.pid)
            return blad
        if nazwa == "przegladarka":
            return s.przegladarka.skanuj()
        typ = s.projekt.get("typ") or "porzadkowanie"
        if nazwa not in dict(KROKI[typ]):
            return "Nieznany krok."
        if nazwa in ZMIENIAJACE and not dane.get("potwierdzam"):
            return "Potwierdź — ten krok zmienia pliki na dysku."
        if nazwa == "skan":
            return s.rozpocznij_skan()
        if nazwa == "dup":
            return s.szukaj_duplikatow()
        if nazwa == "analiza":
            return s.analizuj()
        if nazwa == "plan":
            return s.generuj_plan()
        if nazwa == "wykonanie":
            return s.wykonaj(usun_puste=True, usun_oryginaly=True)
        if nazwa == "usuwanie":
            return s.usun_odlozone(None, True)
        return "Nieznany krok."
