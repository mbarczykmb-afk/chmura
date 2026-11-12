"""✈ Generator wypraw: oś czasu Google (eksport z telefonu: semanticSegments) → dziennik wypraw dla Podróży.

Bez żadnych danych osobistych w kodzie: dom jest wykrywany sam (miejsce, w którym spędzasz najwięcej czasu, albo
wizyty oznaczone przez Google jako „HOME”), wyprawa to pobyt dalej niż 100 km od domu albo lot. Nazwy miejsc: offline
(najbliższa miejscowość PL / kraj z wbudowanej bazy) i — gdy zaznaczysz — z OpenStreetMap (Nominatim, 1 zapytanie/s,
wyniki zapamiętane w places_cache.json; do serwisu trafiają tylko współrzędne odwiedzonych miejsc, nic więcej).
Wynik: <dane>/podroze/dane/sample-trips.json (poprzedni plik zostaje jako kopia .poprzedni).
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from . import miejsca, plik_json, podroze

LOG = logging.getLogger("katalogator.wyprawy")

PROMIEN_KM = 100.0     # dalej niż tyle od domu = poza domem
LUKA_DNI = 2.5         # przerwa między zdarzeniami „poza domem” kończąca wyprawę
MIN_ZDARZEN = 5        # krótszy pobyt bez lotu to nie wyprawa
OKOLICA_DOMU_KM = 15.0  # miejscowości tak blisko domu nie nazywają wyprawy
OSM_MAKS = 400         # najwyżej tyle nowych zapytań do OpenStreetMap w jednym uruchomieniu (reszta przy następnym)
MIESIACE = ["styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec", "sierpień", "wrzesień",
            "październik", "listopad", "grudzień"]
GRADIENTY = ["from-teal-600 to-emerald-700", "from-sky-600 to-blue-700", "from-amber-600 to-orange-700",
             "from-purple-600 to-pink-700", "from-rose-600 to-red-800", "from-indigo-600 to-slate-800",
             "from-emerald-700 to-slate-800", "from-cyan-700 to-slate-800"]

_stan_przerwij = threading.Event()


class Przerwano(Exception):
    pass


def przerwij() -> None:
    _stan_przerwij.set()


# --- współrzędne i czas --------------------------------------------------------------------------------------------------
def wsp(v):
    """Współrzędne z formatów Google: „50.1°, 19.9°”, „geo:50.1,19.9”, {latLng}, {latitudeE7, longitudeE7} → (lat, lon)."""
    if not v:
        return None
    if isinstance(v, dict):
        if v.get("latLng"):
            return wsp(v["latLng"])
        if v.get("latitude") is not None and v.get("longitude") is not None:
            return _ok(float(v["latitude"]), float(v["longitude"]))
        if v.get("latitudeE7") is not None and v.get("longitudeE7") is not None:
            return _ok(v["latitudeE7"] / 1e7, v["longitudeE7"] / 1e7)
        return None
    if isinstance(v, str):
        cz = v.replace("°", "").replace("geo:", "").strip().split(",")
        if len(cz) >= 2:
            try:
                return _ok(float(cz[0]), float(cz[1]))
            except ValueError:
                return None
    return None


def _ok(lat: float, lon: float):
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


def odl_km(a, b) -> float:
    R = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _czas(s: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
    except ValueError:
        return None


def _godz(a: str | None, b: str | None) -> float:
    ta, tb = _czas(a), _czas(b)
    return max(0.0, (tb - ta).total_seconds() / 3600) if ta and tb else 0.0


# --- odczyt pliku -----------------------------------------------------------------------------------------------------------
def wczytaj(plik: str) -> list[dict]:
    """semanticSegments z pliku .json albo .zip (największy .json w archiwum)."""
    p = Path(plik)
    if not p.is_file():
        raise ValueError("Nie ma takiego pliku.")
    if p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as z:
            js = sorted((i for i in z.infolist() if i.filename.lower().endswith(".json")), key=lambda i: -i.file_size)
            if not js:
                raise ValueError("W archiwum ZIP nie ma pliku .json z osią czasu.")
            with z.open(js[0]) as f:
                dane = json.load(f)
    else:
        with open(p, "r", encoding="utf-8") as f:
            dane = json.load(f)
    seg = dane.get("semanticSegments") if isinstance(dane, dict) else None
    if not isinstance(seg, list) or not seg:
        raise ValueError("To nie wygląda na eksport osi czasu z telefonu (brak „semanticSegments”). W Google Maps: "
                         "Ustawienia → Twoja oś czasu → Eksportuj dane z osi czasu — plik Timeline.json.")
    return seg


# --- analiza -----------------------------------------------------------------------------------------------------------------
def zdarzenia(segmenty: list[dict]) -> list[dict]:
    """Wizyty (place) i przejazdy / loty / spacery (activity) w jednym formacie."""
    wynik = []
    for s in segmenty:
        st, en = s.get("startTime"), s.get("endTime")
        if not st:
            continue
        if "visit" in s:
            tc = (s["visit"] or {}).get("topCandidate") or {}
            c = wsp(tc.get("placeLocation"))
            if c:
                wynik.append({"type": "place", "startTime": st, "endTime": en or st, "date": st[:10], "lat": c[0], "lon": c[1],
                              "home": tc.get("semanticType") == "HOME", "placeId": tc.get("placeId") or ""})
        elif "activity" in s:
            a = s["activity"] or {}
            typ = (a.get("topCandidate") or {}).get("type", "UNKNOWN")
            sc, ec = wsp(a.get("start")), wsp(a.get("end"))
            sciezka = [c for c in (wsp(p.get("point")) for p in s.get("timelinePath") or []) if c]
            wynik.append({"type": "activity", "startTime": st, "endTime": en or st, "date": st[:10], "activityType": typ,
                          "distanceMeters": float(a.get("distanceMeters") or 0), "startCoords": sc, "endCoords": ec,
                          "pathPoints": sciezka})
    return wynik


def wykryj_dom(zd: list[dict]):
    """Dom: wizyty oznaczone „HOME” (najczęstsza komórka 0,02°), w razie braku — miejsce o największym czasie pobytu."""
    def komorka(e):
        return (round(e["lat"] / 0.02), round(e["lon"] / 0.02))
    wizyty = [e for e in zd if e["type"] == "place"]
    if not wizyty:
        return None
    dom = [e for e in wizyty if e.get("home")]
    licz: Counter = Counter()
    if dom:
        for e in dom:
            licz[komorka(e)] += 1
    else:
        for e in wizyty:
            licz[komorka(e)] += max(0.05, _godz(e["startTime"], e["endTime"]))
    k = licz.most_common(1)[0][0]
    w = [e for e in (dom or wizyty) if komorka(e) == k]
    return (sum(e["lat"] for e in w) / len(w), sum(e["lon"] for e in w) / len(w))


def wyprawy_z_zdarzen(zd: list[dict], dom, promien_km: float = PROMIEN_KM) -> list[list[dict]]:
    for e in zd:
        if e["type"] == "place":
            e["dom_km"] = odl_km(dom, (e["lat"], e["lon"]))
        else:   # przejazd z / do domu też należy do wyprawy: liczy się dalszy z końców
            e["dom_km"] = max([odl_km(dom, c) for c in (e.get("startCoords"), e.get("endCoords")) if c] or [0.0])
    daleko = sorted((e for e in zd if e["dom_km"] > promien_km or e.get("activityType") == "FLYING"),
                    key=lambda e: e["startTime"])
    wyprawy, biezaca = [], []

    def zamknij():
        if biezaca and (len(biezaca) >= MIN_ZDARZEN or any(x.get("activityType") == "FLYING" for x in biezaca)):
            wyprawy.append(list(biezaca))
    for e in daleko:
        if biezaca:
            a, b = _czas(biezaca[-1]["startTime"]), _czas(e["startTime"])
            if a and b and (b - a).total_seconds() / 86400 > LUKA_DNI:
                zamknij()
                biezaca = []
        biezaca.append(e)
    zamknij()
    return wyprawy


# --- nazwy ------------------------------------------------------------------------------------------------------------------
def _nazwy_krajow() -> dict[str, str]:
    wynik: dict[str, str] = {}
    for nazwa, kod in miejsca.KRAJE_NAZWY.items():
        wynik.setdefault(kod, nazwa[:1].upper() + nazwa[1:])
    return wynik


def flaga(kod: str) -> str:
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in kod.upper()) if len(kod) == 2 and kod.isalpha() else "🗺️"


_KAT_OSM = {"hotel": ("lodging", "🏨"), "guest_house": ("lodging", "🏨"), "hostel": ("lodging", "🏨"), "apartment": ("lodging", "🏨"),
            "motel": ("lodging", "🏨"), "alpine_hut": ("lodging", "🏔️"), "restaurant": ("food", "🍽️"), "cafe": ("food", "☕"),
            "fast_food": ("food", "🍽️"), "bar": ("food", "🍽️"), "pub": ("food", "🍽️"), "peak": ("attraction", "⛰️"),
            "volcano": ("attraction", "⛰️"), "beach": ("attraction", "🏖️"), "viewpoint": ("attraction", "🌄"),
            "museum": ("attraction", "🏛️"), "castle": ("attraction", "🏰"), "monument": ("attraction", "🏛️"),
            "aerodrome": ("transit", "✈️"), "station": ("transit", "🚆"), "bus_stop": ("transit", "🚌")}


def opisz_osm(dane: dict) -> dict:
    """Odpowiedź Nominatim → {name, city, country, category, icon} (jak w dawnym enrich_places_osm)."""
    a = dane.get("address") or {}
    typ = dane.get("type") or ""
    nazwa = ((dane.get("namedetails") or {}).get("name:pl") or (dane.get("namedetails") or {}).get("name") or dane.get("name") or "").strip()
    miasto = a.get("city") or a.get("town") or a.get("village") or a.get("municipality") or ""
    droga = a.get("road") or a.get("pedestrian") or a.get("footway")
    kat, ikona = _KAT_OSM.get(typ) or _KAT_OSM.get(a.get("tourism") or "") or _KAT_OSM.get(a.get("amenity") or "") or ("attraction", "📍")
    if len(nazwa) > 1:
        wys = f"{nazwa} ({miasto})" if miasto and miasto.lower() not in nazwa.lower() else nazwa
    elif droga:
        wys = f"{droga}, {miasto}" if miasto else droga
    elif miasto:
        wys = miasto
    else:
        wys = (dane.get("display_name") or "").split(",")[0]
    return {"name": wys or "Odwiedzone miejsce", "city": miasto, "country": a.get("country") or "", "category": kat, "icon": ikona}


def _osm(lat: float, lon: float) -> dict | None:
    url = "https://nominatim.openstreetmap.org/reverse?" + urllib.parse.urlencode(
        {"format": "json", "lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "zoom": 18, "addressdetails": 1, "namedetails": 1,
         "accept-language": "pl"})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Katalogator (dziennik wypraw)"}),
                                    timeout=15) as r:  # noqa: S310 — stały adres serwisu
            return opisz_osm(json.loads(r.read().decode("utf-8")))
    except Exception as e:  # noqa: BLE001 — brak sieci / limit: miejsce zostaje z nazwą offline
        LOG.info("OSM: %s", e)
        return None


# --- budowa wypraw --------------------------------------------------------------------------------------------------------------
def zbuduj(wyprawy: list[list[dict]], dom, cache: dict, postep=None, przerwij_fn=None, osm: bool = False) -> list[dict]:
    kraje = _nazwy_krajow()
    kraj_domu = miejsca.najblizsze(*dom)[0] if dom else ""
    if osm:   # nazwy miejsc z OpenStreetMap — tylko dla miejsc spoza okolicy domu, z zapamiętywaniem wyników
        do_zapytan = []
        for ev_list in wyprawy:
            for e in ev_list:
                if e["type"] == "place" and not e.get("home") and e["dom_km"] > OKOLICA_DOMU_KM:
                    k = f"{e['lat']:.4f},{e['lon']:.4f}"
                    if k not in cache and (e["lat"], e["lon"]) not in [x[1] for x in do_zapytan]:
                        do_zapytan.append((k, (e["lat"], e["lon"])))
        do_zapytan = do_zapytan[:OSM_MAKS]
        for i, (k, (la, lo)) in enumerate(do_zapytan, 1):
            if przerwij_fn and przerwij_fn():
                raise Przerwano()
            if postep:
                postep(i, len(do_zapytan), f"Nazwy miejsc z OpenStreetMap: {i} z {len(do_zapytan)}")
            w = _osm(la, lo)
            if w:
                cache[k] = w
            time.sleep(1.1)   # limit serwisu: 1 zapytanie na sekundę

    def z_cache(lat, lon):
        w = cache.get(f"{lat:.4f},{lon:.4f}")
        if w:
            return w
        for k, v in cache.items():
            la, lo = k.split(",")
            if abs(float(la) - lat) < 0.0015 and abs(float(lo) - lon) < 0.0015:
                return v
        return None

    wynik = []
    for idx, ev_list in enumerate(wyprawy):
        dni_wyp = sorted({e["date"] for e in ev_list})
        d0, d1 = dni_wyp[0], dni_wyp[-1]
        dt0, dt1 = datetime.strptime(d0, "%Y-%m-%d"), datetime.strptime(d1, "%Y-%m-%d")
        czas_kraju: Counter = Counter()
        czas_miasta: Counter = Counter()
        nazwy_miejsc = set()
        dni: dict[str, list] = {}
        for e in ev_list:
            dni.setdefault(e["date"], []).append(e)
            if e["type"] == "place":
                kraj = miejsca.najblizsze(e["lat"], e["lon"])[0]
                h = max(0.1, _godz(e["startTime"], e["endTime"]))
                if kraj:
                    czas_kraju[kraj] += h
                if e["dom_km"] > OKOLICA_DOMU_KM and not e.get("home"):
                    w = z_cache(e["lat"], e["lon"])
                    miasto = (w or {}).get("city") or (miejsca.etykieta(e["lat"], e["lon"]) if not miejsca.etykieta(e["lat"], e["lon"]).startswith("@") else "")
                    if miasto:
                        czas_miasta[miasto] += h
        top_kraje = [k for k, _ in czas_kraju.most_common(3) if k]
        obce = [k for k in top_kraje if k != kraj_domu]
        if obce:
            cel = " i ".join(kraje.get(k, k) for k in obce[:2])
            if czas_miasta and len(obce) == 1:
                cel += f" ({czas_miasta.most_common(1)[0][0]})"
            odznaka = f"{cel} • za granicą"
            ikona = flaga(obce[0])
        elif czas_miasta:
            cel = czas_miasta.most_common(1)[0][0]
            odznaka = f"{cel} • wyjazd"
            ikona = "📍"
        else:
            cel, odznaka, ikona = "Wyprawa", "Podróż", "🗺️"
        tytul = f"{cel} ({MIESIACE[dt0.month - 1].capitalize()} {dt0.year})"
        gradient = GRADIENTY[sum(map(ord, cel)) % len(GRADIENTY)]

        dni_dane, suma_pieszo, suma_auto, suma_lot = [], 0.0, 0.0, 0.0
        for nr, d in enumerate(sorted(dni), start=1):
            pieszo = auto = 0.0
            sciezka, zdarzenia_dnia = [], []
            for e in sorted(dni[d], key=lambda x: x["startTime"]):
                t0, t1 = e["startTime"][11:16], e["endTime"][11:16]
                if e["type"] == "place":
                    w = z_cache(e["lat"], e["lon"])
                    if e.get("home") or e["dom_km"] <= 1.0:
                        nazwa, miasto, kat, ik = "Dom", "", "home", "🏠"
                    elif w:
                        nazwa, miasto, kat, ik = w["name"], w.get("city", ""), w.get("category", "attraction"), w.get("icon", "📍")
                    else:
                        etyk = miejsca.etykieta(e["lat"], e["lon"])
                        nazwa = kraje.get(etyk[1:], "Odwiedzone miejsce") if etyk.startswith("@") else etyk
                        miasto = "" if etyk.startswith("@") else etyk
                        kat, ik = "attraction", "📍"
                    nazwy_miejsc.add(nazwa)
                    sciezka.append([e["lat"], e["lon"]])
                    zdarzenia_dnia.append({"type": "place", "time": f"{t0} - {t1}", "startTime": e["startTime"], "endTime": e["endTime"],
                                           "name": nazwa, "city": miasto, "category": kat, "icon": ik, "lat": e["lat"], "lon": e["lon"]})
                else:
                    typ, dyst = e["activityType"], e["distanceMeters"]
                    if typ == "FLYING":
                        suma_lot += dyst
                        etykieta, ik = "Lot samolotem", "✈️"
                    elif "WALK" in typ or "HIKE" in typ:
                        pieszo += dyst
                        etykieta, ik = "Piesza wędrówka", "🥾"
                    elif "VEHICLE" in typ or "CAR" in typ:
                        auto += dyst
                        etykieta, ik = "Przejazd samochodem", "🚗"
                    else:
                        etykieta, ik = "Spacer", "🚶"
                    if e["pathPoints"]:
                        sciezka += [list(p) for p in e["pathPoints"]]
                    elif e["startCoords"] and e["endCoords"]:
                        sciezka += [list(e["startCoords"]), list(e["endCoords"])]
                    zdarzenia_dnia.append({"type": "activity", "time": f"{t0} - {t1}", "startTime": e["startTime"], "endTime": e["endTime"],
                                           "label": etykieta, "distanceStr": f"{dyst / 1000:.1f} km" if dyst >= 1000 else f"{dyst:.0f} m",
                                           "distanceMeters": dyst, "activityType": typ, "icon": ik,
                                           "startCoords": e["startCoords"], "endCoords": e["endCoords"]})
            suma_pieszo += pieszo
            suma_auto += auto
            dni_dane.append({"dayNumber": nr, "date": d, "title": f"Dzień {nr}: {d}",
                             "description": f"Trasa dnia ({round(pieszo / 1000, 1)} km pieszo, {round(auto / 1000, 1)} km autem)",
                             "walkDistanceKm": round(pieszo / 1000, 1), "driveDistanceKm": round(auto / 1000, 1),
                             "events": zdarzenia_dnia, "path": sciezka, "mountainTracks": []})
        wynik.append({"id": f"trip-{d0}-{idx}", "title": tytul, "destination": cel, "badge": odznaka, "icon": ikona,
                      "gradient": gradient, "dates": f"{d0} – {d1}", "startDate": d0, "endDate": d1,
                      "durationDays": (dt1 - dt0).days + 1, "totalKmWalk": round(suma_pieszo / 1000, 1),
                      "totalKmDrive": round(suma_auto / 1000, 1), "totalKmFlight": round(suma_lot / 1000, 0),
                      "placesCount": len(nazwy_miejsc), "highlights": sorted(nazwy_miejsc)[:8], "days": dni_dane})
    wynik.sort(key=lambda t: t["startDate"], reverse=True)
    return wynik


# --- całość -----------------------------------------------------------------------------------------------------------------------
GENEROWANE = {"id", "title", "destination", "badge", "icon", "gradient", "dates", "startDate", "endDate", "durationDays",
              "totalKmWalk", "totalKmDrive", "totalKmFlight", "placesCount", "highlights", "days"}


def generuj(katalog, plik: str, osm: bool = False, postep=None, przerwij_fn=None, dom=None) -> dict:
    """Plik osi czasu → sample-trips.json w folderze danych Podróży. Dopiski wcześniejszych wypraw (zdjęcia,
    rezerwacje) o tej samej dacie początku są przenoszone do nowych."""
    def p(z, w, k):
        if postep:
            postep(z, w, k)
    p(0, 0, "Wczytuję plik osi czasu…")
    seg = wczytaj(plik)
    p(0, 0, f"Analizuję {len(seg):,} wpisów…".replace(",", " "))
    zd = zdarzenia(seg)
    dom = dom or wykryj_dom(zd)
    if not dom:
        raise ValueError("W pliku nie ma wizyt — nie da się ustalić, gdzie mieszkasz.")
    wyp = wyprawy_z_zdarzen(zd, dom)
    d = podroze.folder_danych(katalog)
    d.mkdir(parents=True, exist_ok=True)
    cache_plik = d / "places_cache.json"
    try:
        cache = plik_json.czytaj(cache_plik) or {}
    except (OSError, ValueError):
        cache = {}
    try:
        trasy = zbuduj(wyp, dom, cache, p, przerwij_fn, osm)
    finally:
        if osm and cache:
            plik_json.zapisz(cache_plik, cache, 1)
    cel = d / "sample-trips.json"
    if cel.is_file():   # dopiski z poprzednich wypraw o tej samej dacie początku
        try:
            stare = {t.get("startDate"): t for t in (plik_json.czytaj(cel) or {}).get("trips", []) if isinstance(t, dict)}
        except (OSError, ValueError):
            stare = {}
        for t in trasy:
            s = stare.get(t["startDate"])
            if s:
                t.update({k: v for k, v in s.items() if k not in GENEROWANE})
        try:
            os.replace(cel, d / "sample-trips.json.poprzedni")
        except OSError:
            pass
    plik_json.zapisz(cel, {"trips": trasy, "totalTrips": len(trasy), "generatedAt": datetime.now().isoformat(),
                           "dom": {"lat": round(dom[0], 3), "lon": round(dom[1], 3)}}, 1)
    podroze._licznik.clear()
    try:   # ślady GPS ze Stravy / Intervals.icu dla nowych wypraw (z pamięci, bez sieci)
        from . import slady
        slady.zloz(katalog)
    except Exception:  # noqa: BLE001
        LOG.exception("Wyprawy: składanie śladów")
    return {"wyprawy": len(trasy), "zdarzen": len(zd), "dom": dom}


def generuj_w_tle(katalog, plik: str, osm: bool = False) -> dict:
    """Uruchamia generator w wątku; postęp w podroze._import (ten sam pasek co przy imporcie)."""
    plik = str(plik or "").strip().strip('"')
    if not plik:
        return {"blad": "Wskaż plik osi czasu (Timeline.json z telefonu)."}
    if not Path(plik).is_file():
        return {"blad": "Nie ma takiego pliku: " + plik}
    with podroze._blokada:
        if podroze._import["trwa"]:
            return {"blad": "Poczekaj, aż skończy się import."}
        podroze._import.update(trwa=True, zrobione=0, wszystkie=0, komunikat="Zaczynam…", blad="")
    _stan_przerwij.clear()

    def postep(z, w, k):
        with podroze._blokada:
            podroze._import.update(zrobione=z, wszystkie=w, komunikat=k)

    def praca():
        try:
            w = generuj(katalog, plik, osm, postep, _stan_przerwij.is_set)
            with podroze._blokada:
                podroze._import.update(trwa=False, koniec=time.time(),
                                       komunikat=f"Gotowe — {w['wyprawy']} wypraw z {w['zdarzen']:,} wpisów osi czasu.".replace(",", " "))
        except Przerwano:
            with podroze._blokada:
                podroze._import.update(trwa=False, komunikat="Przerwano — nazwy z OpenStreetMap zapamiętane, kolejne uruchomienie dokończy.")
        except (ValueError, OSError, json.JSONDecodeError, zipfile.BadZipFile) as e:
            LOG.exception("Wyprawy: błąd")
            with podroze._blokada:
                podroze._import.update(trwa=False, blad=f"Nie udało się: {e}", komunikat="")
    threading.Thread(target=praca, daemon=True, name="wyprawy").start()
    return {"ok": True}
