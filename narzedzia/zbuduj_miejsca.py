"""Buduje katalogator/dane/miejsca.tsv.gz z bazy GeoNames (cities1000, CC BY 4.0).

Źródło: plik geocode.gz z pakietu PyPI `reverse_geocode` (dane GeoNames z polskimi znakami):
    pip download --no-deps reverse_geocode && unzip reverse_geocode-*.whl
    python narzedzia/zbuduj_miejsca.py reverse_geocode/geocode.gz

Wynik (TSV): lat, lon, kod_kraju, nazwa (tylko PL), ludność (tylko PL).
Dzielnice dużych miast (Mokotów, „Rejon ulicy…”) są zamieniane na nazwę miasta.
"""

import gzip
import json
import math
import re
import sys
from pathlib import Path

POPRAWKI = {"Warsaw": "Warszawa", "Bielsko-Biala": "Bielsko-Biała", "Białołeka": "Białołęka",
            "Środmieście": "Śródmieście"}
# Promień (km), w którym mniejsze miejsca uznajemy za dzielnice dużego miasta.
PROMIENIE = {"Warszawa": 13, "Kraków": 10, "Łódź": 8, "Wrocław": 9, "Poznań": 7, "Gdańsk": 7.5,
             "Szczecin": 9, "Bydgoszcz": 7, "Lublin": 6, "Katowice": 5, "Białystok": 6, "Gdynia": 6}
DOMYSLNY_PROMIEN = 4  # pozostałe miasta > 100 tys.
# Osobne miasta leżące blisko dużych — nie wchłaniamy.
OSOBNE = {"Sopot", "Luboń", "Zgierz", "Konstantynów Łódzki", "Pruszków", "Ząbki", "Marki", "Łomianki",
          "Piastów", "Chorzów", "Siemianowice Śląskie", "Mysłowice", "Świętochłowice", "Czeladź",
          "Ruda Śląska", "Swarzędz", "Sulejówek", "Kobyłka", "Wieliczka", "Skawina", "Police",
          "Józefów", "Otwock", "Legionowo", "Piaseczno", "Rumia", "Reda", "Pruszcz Gdański",
          "Świdnik", "Wasilków", "Zielonka", "Raszyn", "Michałowice", "Czechowice-Dziedzice",
          "Piekary Śląskie", "Radzionków", "Będzin", "Wojkowice", "Tarnowskie Góry", "Siemianowice"}
DZIELNICA = re.compile(r"^(Rejon|Osiedle|Powstańców|Kolonia|Zespół)\b")


def km(a, b):
    return math.hypot((a[0] - b[0]) * 111.2, (a[1] - b[1]) * 111.2 * math.cos(math.radians(a[0])))


def main(zrodlo, cel):
    dane = json.load(gzip.open(zrodlo, "rt", encoding="utf-8"))
    pl, reszta = [], []
    for x in dane:
        if x["country_code"] == "PL":
            nazwa = POPRAWKI.get(x["city"], x["city"])
            pl.append({"n": nazwa, "p": (x["latitude"], x["longitude"]), "l": x.get("population") or 0})
        else:
            reszta.append((round(x["latitude"], 2), round(x["longitude"], 2), x["country_code"]))
    # Miasta główne: > 100 tys. i same nie leżą w promieniu większego miasta (Ursynów to dzielnica).
    duze = []
    for m in sorted((m for m in pl if m["l"] >= 100_000), key=lambda m: -m["l"]):
        if m["n"] in OSOBNE or not any(km(m["p"], c["p"]) < PROMIENIE.get(c["n"], DOMYSLNY_PROMIEN)
                                       and m["l"] * 2.5 <= c["l"] for c in duze):
            duze.append(m)
    for m in pl:
        m["etykieta"] = m["n"]
        if m["n"] in OSOBNE:
            continue
        najblizsze = None
        for c in duze:
            if c is m or m["l"] * 2.5 > c["l"]:
                continue
            d = km(m["p"], c["p"])
            r = PROMIENIE.get(c["n"], DOMYSLNY_PROMIEN)
            if d < r and (najblizsze is None or d < najblizsze[0]):
                najblizsze = (d, c["n"])
        if najblizsze:
            m["etykieta"] = najblizsze[1]
        elif DZIELNICA.match(m["n"]):
            m["etykieta"] = None  # bez miasta w pobliżu — pomijamy
    wiersze = []
    for m in pl:
        if m["etykieta"]:
            wiersze.append(f"{m['p'][0]:.4f}\t{m['p'][1]:.4f}\tPL\t{m['etykieta']}\t{m['l']}")
    widziane = set()
    for lat, lon, cc in reszta:
        if (lat, lon) not in widziane:
            widziane.add((lat, lon))
            wiersze.append(f"{lat}\t{lon}\t{cc}\t\t")
    with gzip.open(cel, "wt", encoding="utf-8", compresslevel=9) as f:
        f.write("\n".join(wiersze) + "\n")
    wchloniete = [(m["n"], m["etykieta"]) for m in pl if m["etykieta"] and m["etykieta"] != m["n"]]
    print(f"PL: {len(pl)}, zapisano {len(wiersze)} punktów, dzielnic wchłoniętych: {len(wchloniete)}")
    return wchloniete


if __name__ == "__main__":
    w = main(sys.argv[1], Path(__file__).resolve().parents[1] / "katalogator" / "dane" / "miejsca.tsv.gz")
    if "-v" in sys.argv:
        for a, b in sorted(w, key=lambda x: x[1]):
            try:
                print(f"  {a} -> {b}")
            except BrokenPipeError:
                break
