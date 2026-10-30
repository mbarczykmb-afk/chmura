"""📍 Zdjęcia bez GPS: propozycje lokalizacji do przejrzenia (jak duplikaty — grupa, propozycja na mapie, decyzja należy do Ciebie).

Skąd propozycje, od najpewniejszych:
  1. ślad aktywności z tej samej chwili — Strava / Intervals.icu (slady.py) albo pliki GPX z folderu (np. eksport Sports Trackera);
     punkt zdjęcia jest wyliczany z czasu zdjęcia na śladzie;
  2. zdjęcie z GPS zrobione w ciągu kilku minut (inny aparat, telefon);
  3. oś czasu Google z Podróży — wizyta w miejscu albo przejazd w tym czasie;
  4. GeoCLIP — rozpoznanie miejsca z samego obrazu (geoclip.py), tylko dla zdjęć bez żadnego innego tropu; przybliżone.
Nic nie jest zapisywane samo: przyjęcie grupy zapisuje lokalizację zwykłą drogą Przeglądarki (/api/g/lokalizacja — EXIF lub .xmp,
z Cofnij), a odrzucenie zapamiętuje, żeby ta sama propozycja nie wracała.

Czas zdjęcia i czas śladu porównujemy jako czas lokalny (EXIF nie ma strefy; Strava i Intervals podają start lokalnie). GPX ma czas
UTC — przeliczamy go na strefę tego komputera, więc dla wypraw w innej strefie propozycje z GPX mogą być przesunięte.
"""
from __future__ import annotations

import bisect
import datetime as dt
import hashlib
import json
import logging
import math
import os
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

LOG = logging.getLogger("katalogator.bez_gps")

KATALOG: Path | None = None   # folder danych programu (ślady, Podróże, modele) — ustawia aplikacja
MARGINES_SLADU_S = 300        # zdjęcie do 5 min przed startem / po końcu śladu
SASIAD_PEWNY_S = 600          # zdjęcie z GPS w ciągu 10 min
SASIAD_LUZNY_S = 3600         # … w ciągu godziny (niska pewność)
MARGINES_WIZYTY_S = 600
PRZERWA_GRUPY_S = 2 * 3600
MAKS_GRUPA = 300
GEOCLIP_PROBKI = 3

SCHEMAT = """
CREATE TABLE IF NOT EXISTS g_gps_decyzje (sciezka TEXT NOT NULL, zrodlo TEXT NOT NULL, czas REAL NOT NULL, PRIMARY KEY (sciezka, zrodlo));
CREATE TABLE IF NOT EXISTS g_gps_geoclip (sciezka TEXT PRIMARY KEY, mtime REAL NOT NULL, wynik TEXT NOT NULL);
"""

_STANY: dict[str, dict] = {}
_WYNIKI: dict[str, dict] = {}
_BLOKADA = threading.Lock()
_GPX: dict[str, tuple[float, list]] = {}   # plik → (mtime, aktywności) — pamięć odczytanych GPX


# --- drobiazgi -------------------------------------------------------------------------------------------------------------
def km(a, b) -> float:
    r = math.radians
    h = math.sin(r(b[0] - a[0]) / 2) ** 2 + math.cos(r(a[0])) * math.cos(r(b[0])) * math.sin(r(b[1] - a[1]) / 2) ** 2
    return 12742 * math.asin(math.sqrt(min(1.0, h)))


def _czas(s) -> dt.datetime | None:
    """Czas lokalny bez strefy z napisu ISO (z EXIF, Stravy, osi czasu Google — strefę pomijamy, liczy się godzina na zegarku)."""
    try:
        return dt.datetime.fromisoformat(str(s)[:19])
    except (TypeError, ValueError):
        return None


def _db(g):
    db = g._db()
    if not getattr(g, "_schemat_gps", False):   # tabele raz na galerię — executescript to zapis (blokada bazy przy odpytywaniu stanu)
        db.executescript(SCHEMAT)
        g._schemat_gps = True
    return db


def ustawienia(g) -> dict:
    db = _db(g)
    try:
        r = db.execute("SELECT wartosc FROM g_ustawienia WHERE klucz='gps_propozycje'").fetchone()
    finally:
        db.close()
    try:
        d = json.loads(r[0]) if r else {}
    except ValueError:
        d = {}
    return d if isinstance(d, dict) else {}


def zapisz_ustawienia(g, nowe: dict) -> dict:
    d = ustawienia(g)
    if "folder_gpx" in nowe:
        f = str(nowe.get("folder_gpx") or "").strip().strip('"')
        if f and not os.path.isdir(f):
            return {"blad": "Nie ma takiego folderu: " + f}
        d["folder_gpx"] = os.path.normpath(f) if f else ""
    if "geoclip" in nowe:
        d["geoclip"] = bool(nowe["geoclip"])
    db = _db(g)
    try:
        db.execute("INSERT OR REPLACE INTO g_ustawienia (klucz, wartosc) VALUES ('gps_propozycje', ?)", (json.dumps(d),))
        db.commit()
    finally:
        db.close()
    return d


# --- źródła ----------------------------------------------------------------------------------------------------------------
def domyslny_folder_gpx() -> str:
    """Typowe miejsce eksportu Sports Trackera (folder projektu Szczyty) — podpowiedź w widoku."""
    for p in (Path("C:/Claude/Szczyty/sports-tracker"), Path.home() / "Documents" / "Claude" / "Szczyty" / "sports-tracker"):
        try:
            if p.is_dir():
                return str(p)
        except OSError:
            pass
    return ""


def _pamiec_gpx(p: Path) -> Path | None:
    return Path(KATALOG) / "gpx-pamiec" / (hashlib.sha1(str(p).encode("utf-8")).hexdigest()[:20] + ".json") if KATALOG else None


def _gpx_plik(p: Path) -> list[dict]:
    """Ślady z jednego pliku GPX: [{start, koniec, nazwa, pts:[(sekundy, lat, lon)]}] (czas lokalny tego komputera).
    Punkt co ≥ 10 s; wynik zapamiętany w pamięci i na dysku (setki MB GPX czytamy raz)."""
    try:
        st = p.stat()
    except OSError:
        return []
    k, znak = str(p), [st.st_mtime, st.st_size]
    if k in _GPX and _GPX[k][0] == znak:
        return _GPX[k][1]
    pam = _pamiec_gpx(p)
    if pam:
        try:
            d = json.loads(pam.read_text(encoding="utf-8"))
            if d.get("znak") == znak:
                wynik = [{**a, "start": dt.datetime.fromisoformat(a["start"]), "koniec": dt.datetime.fromisoformat(a["koniec"]),
                          "pts": [tuple(x) for x in a["pts"]]} for a in d["akt"]]
                _GPX[k] = (znak, wynik)
                return wynik
        except (OSError, ValueError, KeyError, TypeError):
            pass
    pkt: list[tuple[dt.datetime, float, float]] = []
    nazwa = ""
    try:
        for _, el in ET.iterparse(p, events=("end",)):
            tag = el.tag.rsplit("}", 1)[-1]
            if tag == "name" and not nazwa and el.text:
                nazwa = el.text.strip()[:120]
            elif tag in ("trkpt", "rtept"):
                t = next((c.text for c in el if c.tag.rsplit("}", 1)[-1] == "time" and c.text), None)
                try:
                    la, lo = float(el.get("lat")), float(el.get("lon"))
                    c = dt.datetime.fromisoformat(t.strip().replace("Z", "+00:00")) if t else None
                except (TypeError, ValueError):
                    c = None
                if c is not None:
                    if c.tzinfo is not None:
                        c = c.astimezone().replace(tzinfo=None)
                    pkt.append((c, la, lo))
                el.clear()
    except (ET.ParseError, OSError):
        pkt = []
    wynik = []
    if len(pkt) >= 2:
        pkt.sort()
        s = pkt[0][0]
        rz, ost = [], None
        for i, (c, la, lo) in enumerate(pkt):
            t = (c - s).total_seconds()
            if ost is None or t - ost >= 10 or i == len(pkt) - 1:
                rz.append((t, round(la, 6), round(lo, 6)))
                ost = t
        wynik = [{"zrodlo": "gpx", "id": p.name, "nazwa": nazwa or p.stem, "typ": "GPX", "start": s, "koniec": pkt[-1][0], "pts": rz}]
    _GPX[k] = (znak, wynik)
    if pam:
        try:
            pam.parent.mkdir(parents=True, exist_ok=True)
            pam.write_text(json.dumps({"znak": znak, "akt": [{**a, "start": a["start"].isoformat(), "koniec": a["koniec"].isoformat()}
                                                            for a in wynik]}), encoding="utf-8")
        except OSError:
            pass
    return wynik


def _slady(katalog, folder_gpx: str) -> list[dict]:
    wynik = []
    if katalog:
        from . import slady
        try:
            wynik += slady.aktywnosci_z_czasem(katalog)
        except Exception:  # noqa: BLE001 — uszkodzona pamięć śladów nie może zatrzymać skanu
            LOG.exception("bez_gps: ślady")
    if folder_gpx and os.path.isdir(folder_gpx):
        for i, p in enumerate(sorted(Path(folder_gpx).rglob("*.gpx"))):
            if i >= 20000:
                break
            wynik += _gpx_plik(p)
    return sorted(wynik, key=lambda a: a["start"])


def _os_czasu(katalog) -> list[dict]:
    """Wizyty i przejazdy z osi czasu Google (dane Podróży): [{od, do, typ, nazwa, a:(lat,lon), b:(lat,lon)}]."""
    if not katalog:
        return []
    from . import podroze
    try:
        d = json.loads((podroze.folder_danych(katalog) / "sample-trips.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    wynik = []
    for t in (d.get("trips") if isinstance(d, dict) else d) or []:
        for dzien in t.get("days") or []:
            for e in dzien.get("events") or []:
                od, do = _czas(e.get("startTime")), _czas(e.get("endTime"))
                if not od or not do or do < od:
                    continue
                if e.get("type") == "place" and isinstance(e.get("lat"), (int, float)) and isinstance(e.get("lon"), (int, float)) \
                        and (e["lat"] or e["lon"]):
                    wynik.append({"od": od, "do": do, "typ": "wizyta", "nazwa": str(e.get("name") or "")[:120],
                                  "a": (float(e["lat"]), float(e["lon"])), "b": None})
                elif e.get("type") == "activity":
                    a, b = e.get("startCoords"), e.get("endCoords")
                    if isinstance(a, list) and isinstance(b, list) and len(a) >= 2 and len(b) >= 2:
                        wynik.append({"od": od, "do": do, "typ": "przejazd", "nazwa": str(e.get("label") or "przejazd")[:80],
                                      "a": (float(a[0]), float(a[1])), "b": (float(b[0]), float(b[1]))})
    return sorted(wynik, key=lambda x: x["od"])


def _na_sladzie(a: dict, t: dt.datetime) -> tuple[float, float]:
    s = (t - a["start"]).total_seconds()
    pts = a["pts"]
    i = bisect.bisect_left([p[0] for p in pts], s)
    if i <= 0:
        return pts[0][1], pts[0][2]
    if i >= len(pts):
        return pts[-1][1], pts[-1][2]
    (t0, la0, lo0), (t1, la1, lo1) = pts[i - 1], pts[i]
    u = 0.0 if t1 == t0 else (s - t0) / (t1 - t0)
    return la0 + (la1 - la0) * u, lo0 + (lo1 - lo0) * u


# --- dopasowanie -----------------------------------------------------------------------------------------------------------
def dopasuj(zdjecia: list[dict], slady_: list[dict], sasiedzi: list[tuple], os_czasu: list[dict], odrzucone: set) -> tuple[list, list]:
    """zdjecia: [{id, sciezka, t}] → (dopasowane: [{…, typ, klucz, lat, lon, pewnosc, opis}], bez_tropu: [zdjęcie]).
    sasiedzi: [(t, lat, lon)] posortowane — zdjęcia z GPS."""
    starty = [a["start"] for a in slady_]
    t_sas = [s[0] for s in sasiedzi]
    od_os = [w["od"] for w in os_czasu]
    dopasowane, reszta = [], []
    for z in zdjecia:
        t = z["t"]
        wynik = None
        # 1. ślad aktywności
        if (z["sciezka"], "slad") not in odrzucone:
            i = bisect.bisect_right(starty, t + dt.timedelta(seconds=MARGINES_SLADU_S))
            for a in reversed(slady_[max(0, i - 40):i]):
                if a["start"] - dt.timedelta(seconds=MARGINES_SLADU_S) <= t <= a["koniec"] + dt.timedelta(seconds=MARGINES_SLADU_S):
                    la, lo = _na_sladzie(a, t)
                    zr = {"strava": "Strava", "intervals": "Intervals.icu", "gpx": "GPX"}.get(a["zrodlo"], a["zrodlo"])
                    wynik = {"typ": "slad", "klucz": f"slad:{a['zrodlo']}:{a['id']}", "lat": la, "lon": lo, "pewnosc": "wysoka",
                             "opis": f"{zr}: {a['nazwa'] or a['typ']}", "akt": a}
                    break
        # 2. zdjęcie z GPS zrobione chwilę wcześniej / później
        sas = None
        if sasiedzi and (z["sciezka"], "sasiad") not in odrzucone:
            j = bisect.bisect_left(t_sas, t)
            kand = [sasiedzi[k] for k in (j - 1, j) if 0 <= k < len(sasiedzi)]
            if kand:
                sas = min(kand, key=lambda s: abs((s[0] - t).total_seconds()))
        roznica = abs((sas[0] - t).total_seconds()) if sas else None
        if not wynik and sas and roznica <= SASIAD_PEWNY_S:
            wynik = {"typ": "sasiad", "klucz": "sasiad", "lat": sas[1], "lon": sas[2], "pewnosc": "wysoka" if roznica <= 180 else "średnia",
                     "opis": f"zdjęcie z GPS {round(roznica / 60) or '<1'} min {'wcześniej' if sas[0] <= t else 'później'}"}
        # 3. oś czasu Google
        if not wynik and os_czasu:
            k = bisect.bisect_right(od_os, t + dt.timedelta(seconds=MARGINES_WIZYTY_S))
            for w in reversed(os_czasu[max(0, k - 30):k]):
                if (z["sciezka"], w["typ"]) in odrzucone:
                    continue
                if w["od"] - dt.timedelta(seconds=MARGINES_WIZYTY_S) <= t <= w["do"] + dt.timedelta(seconds=MARGINES_WIZYTY_S):
                    if w["typ"] == "wizyta":
                        wynik = {"typ": "wizyta", "klucz": f"wizyta:{w['od'].isoformat()}", "lat": w["a"][0], "lon": w["a"][1],
                                 "pewnosc": "średnia", "opis": f"oś czasu Google: {w['nazwa'] or 'wizyta'}"}
                    else:
                        dl = max(1.0, (w["do"] - w["od"]).total_seconds())
                        u = min(1.0, max(0.0, (t - w["od"]).total_seconds() / dl))
                        wynik = {"typ": "przejazd", "klucz": f"przejazd:{w['od'].isoformat()}", "lat": w["a"][0] + (w["b"][0] - w["a"][0]) * u,
                                 "lon": w["a"][1] + (w["b"][1] - w["a"][1]) * u, "pewnosc": "niska",
                                 "opis": f"oś czasu Google: {w['nazwa']} (prosta między początkiem a końcem)"}
                    break
        if not wynik and sas and roznica <= SASIAD_LUZNY_S:
            wynik = {"typ": "sasiad", "klucz": "sasiad", "lat": sas[1], "lon": sas[2], "pewnosc": "niska",
                     "opis": f"zdjęcie z GPS {round(roznica / 60)} min {'wcześniej' if sas[0] <= t else 'później'}"}
        if wynik:
            dopasowane.append({**z, **wynik})
        else:
            reszta.append(z)
    return dopasowane, reszta


def grupuj(dopasowane: list[dict]) -> list[list[dict]]:
    """Kolejne zdjęcia z tego samego źródła (ten sam ślad / wizyta), bez długiej przerwy, w jednej grupie."""
    grupy: list[list[dict]] = []
    for z in sorted(dopasowane, key=lambda x: x["t"]):
        g = grupy[-1] if grupy else None
        if g and g[-1]["klucz"] == z["klucz"] and (z["t"] - g[-1]["t"]).total_seconds() <= PRZERWA_GRUPY_S and len(g) < MAKS_GRUPA \
                and (z["typ"] != "sasiad" or km((g[-1]["lat"], g[-1]["lon"]), (z["lat"], z["lon"])) <= 3):
            g.append(z)
        else:
            grupy.append([z])
    return grupy


def grupuj_reszte(reszta: list[dict]) -> list[list[dict]]:
    """Zdjęcia bez tropu — po dniach (przerwa do 3 h) — dla GeoCLIP."""
    grupy: list[list[dict]] = []
    for z in sorted(reszta, key=lambda x: x["t"]):
        g = grupy[-1] if grupy else None
        if g and z["t"].date() == g[-1]["t"].date() and (z["t"] - g[-1]["t"]).total_seconds() <= 3 * 3600 and len(g) < 200:
            g.append(z)
        else:
            grupy.append([z])
    return grupy


def polacz_geoclip(wyniki: list[list[tuple]]) -> list[tuple[float, float, float]]:
    """Propozycje GeoCLIP dla kilku zdjęć z grupy → skupiska (do 50 km) od najpewniejszego: [(lat, lon, p)]."""
    n = max(1, len(wyniki))
    kand = sorted((w for lista in wyniki for w in lista), key=lambda w: -w[2])
    skupiska: list[list[tuple]] = []
    for w in kand:
        for s in skupiska:
            if km(s[0], w) <= 50:
                s.append(w)
                break
        else:
            skupiska.append([w])
    wynik = []
    for s in skupiska:
        p = sum(w[2] for w in s)
        wynik.append((round(sum(w[0] * w[2] for w in s) / p, 5), round(sum(w[1] * w[2] for w in s) / p, 5), round(p / n, 3)))
    return sorted(wynik, key=lambda w: -w[2])[:4]


# --- skan (w tle) ----------------------------------------------------------------------------------------------------------
def stan(g) -> dict:
    from . import geoclip, slady
    k = str(g.baza)
    with _BLOKADA:
        s = dict(_STANY.get(k) or {"trwa": False, "komunikat": "", "blad": "", "zrobione": 0, "wszystkie": 0})
        w = _WYNIKI.get(k)
    u = ustawienia(g)
    modele = Path(KATALOG) / "modele" if KATALOG else None
    sl = slady.stan(KATALOG) if KATALOG else {"klucze": {}, "ze_sladem": 0, "pobieranie": {}}
    return {**s, "ustawienia": {"folder_gpx": u.get("folder_gpx", ""), "geoclip": bool(u.get("geoclip"))},
            "podpowiedz_gpx": "" if u.get("folder_gpx") else domyslny_folder_gpx(),
            "geoclip_model": geoclip.stan(modele) if modele else {"pobrany": False},
            "slady": {"klucze": sl["klucze"], "ze_sladem": sl["ze_sladem"], "pobieranie": sl["pobieranie"]},
            "podsumowanie": (w or {}).get("podsumowanie"), "zeskanowano": (w or {}).get("czas")}


def start(g, geoclip_wl: bool | None = None) -> dict:
    k = str(g.baza)
    with _BLOKADA:
        if (_STANY.get(k) or {}).get("trwa"):
            return {"blad": "Skan już trwa."}
        _STANY[k] = {"trwa": True, "przerwij": False, "komunikat": "Szukam zdjęć bez GPS…", "blad": "", "zrobione": 0, "wszystkie": 0}
    if geoclip_wl is not None:
        zapisz_ustawienia(g, {"geoclip": geoclip_wl})
    threading.Thread(target=_skan, args=(g,), daemon=True, name="gps-propozycje").start()
    return {"ok": True}


def przerwij(g) -> None:
    with _BLOKADA:
        if str(g.baza) in _STANY:
            _STANY[str(g.baza)]["przerwij"] = True


def _ustaw(g, **z) -> bool:
    with _BLOKADA:
        s = _STANY.setdefault(str(g.baza), {})
        s.update(z)
        return not s.get("przerwij")


def _dokumenty_sql(db) -> str:
    ma = db.execute("SELECT 1 FROM sqlite_master WHERE name='decyzje_dok'").fetchone()
    if ma:
        return ("((lower(wzgledna) LIKE '%dokument%' AND sciezka NOT IN (SELECT sciezka FROM decyzje_dok WHERE dokument=0))"
                " OR sciezka IN (SELECT sciezka FROM decyzje_dok WHERE dokument=1))")
    return "(lower(wzgledna) LIKE '%dokument%')"


def wczytaj(g) -> tuple[list[dict], list[tuple], set]:
    """Zdjęcia bez GPS (z datą z EXIF / nazwy, bez dokumentów), zdjęcia z GPS (sąsiedzi) i odrzucone propozycje."""
    w, arg = g._warunek()
    db = _db(g)
    try:
        dok = _dokumenty_sql(db)
        zdjecia = []
        for rowid, sciezka, data, mtime in db.execute(
                f"""SELECT rowid, sciezka, data, mtime FROM pliki WHERE rodzaj='zdjecie' AND (lat IS NULL OR lon IS NULL)
                    AND data IS NOT NULL AND COALESCE(zrodlo_daty,'') <> 'plik' AND NOT {dok} {w}""", arg):
            t = _czas(data)
            if t:
                zdjecia.append({"id": rowid, "sciezka": sciezka, "t": t, "mtime": mtime})
        sasiedzi = []
        for data, lat, lon in db.execute(
                f"""SELECT data, lat, lon FROM pliki WHERE rodzaj IN ('zdjecie','film') AND lat IS NOT NULL AND lon IS NOT NULL
                    AND data IS NOT NULL AND COALESCE(zrodlo_daty,'') <> 'plik' {w}""", arg):
            t = _czas(data)
            if t and (lat or lon):
                sasiedzi.append((t, float(lat), float(lon)))
        odrzucone = {(s, z) for s, z in db.execute("SELECT sciezka, zrodlo FROM g_gps_decyzje")}
    finally:
        db.close()
    sasiedzi.sort()
    return zdjecia, sasiedzi, odrzucone


def _segment(a: dict, od: dt.datetime, do: dt.datetime) -> list[list[float]]:
    """Fragment śladu wokół zdjęć grupy (±15 min, z punktami tuż przed i tuż po) — do pokazania na mapie."""
    t = [p[0] for p in a["pts"]]
    i0 = max(0, bisect.bisect_left(t, (od - a["start"]).total_seconds() - 900) - 1)
    i1 = min(len(t), bisect.bisect_right(t, (do - a["start"]).total_seconds() + 900) + 1)
    pts = [[round(p[1], 5), round(p[2], 5)] for p in a["pts"][i0:i1]]
    krok = max(1, len(pts) // 300)
    return pts[::krok]


def _grupa_json(gr: list[dict], typ: str, opis: str, pewnosc: str, punkty: list, extra: dict | None = None) -> dict:
    klucz = hashlib.sha1((typ + "|" + gr[0]["sciezka"] + "|" + str(len(gr))).encode()).hexdigest()[:16]
    from . import miejsca   # nazwa miejsca bez internetu: miejscowość w Polsce albo kraj — podpis przy propozycji
    try:
        etyk = miejsca.etykieta(punkty[0][1], punkty[0][2])
        miejsce = miejsca.fraza(etyk) if etyk.startswith("@") else etyk
    except Exception:  # noqa: BLE001 — brak danych miejsc nie może zepsuć przeglądu
        miejsce = ""
    pliki = [{"id": z["id"], "nazwa": os.path.basename(z["sciezka"]), "data": z["t"].isoformat(), "rodzaj": "zdjecie"} for z in gr]
    return {"klucz": klucz, "typ": typ, "opis": opis, "pewnosc": pewnosc, "n": len(gr), "ids": [z["id"] for z in gr], "pliki": pliki, "miejsce": miejsce,
            "od": gr[0]["t"].isoformat(), "do": gr[-1]["t"].isoformat(), "punkty": punkty, **(extra or {})}


def _skan(g) -> None:
    from . import geoclip
    k = str(g.baza)
    try:
        u = ustawienia(g)
        zdjecia, sasiedzi, odrzucone = wczytaj(g)
        _ustaw(g, komunikat=f"Zdjęć bez GPS: {len(zdjecia)} — czytam ślady (pliki GPX za pierwszym razem chwilę trwają)…", wszystkie=len(zdjecia))
        slady_ = _slady(KATALOG, u.get("folder_gpx", ""))
        dopasowane, reszta = dopasuj(zdjecia, slady_, sasiedzi, _os_czasu(KATALOG), odrzucone)
        grupy = []
        for gr in grupuj(dopasowane):
            z0 = gr[0]
            punkty = [[z["id"], round(z["lat"], 6), round(z["lon"], 6)] for z in gr]
            extra = {"slad": _segment(z0["akt"], gr[0]["t"], gr[-1]["t"])} if z0["typ"] == "slad" else {}
            grupy.append(_grupa_json(gr, z0["typ"], z0["opis"], min((z["pewnosc"] for z in gr), key=["niska", "średnia", "wysoka"].index),
                                     punkty, extra))
        # GeoCLIP — tylko zdjęcia bez żadnego tropu
        modele = Path(KATALOG) / "modele" if KATALOG else None
        reszta = [z for z in reszta if (z["sciezka"], "geoclip") not in odrzucone]
        bez = len(reszta)
        if u.get("geoclip") and modele and geoclip.pobrany(modele) and reszta:
            gr_reszty = grupuj_reszte(reszta)
            probki = sum(min(GEOCLIP_PROBKI, len(gr)) for gr in gr_reszty)
            zrobione = 0
            db = _db(g)
            try:
                pamiec = {s: (m, w) for s, m, w in db.execute("SELECT sciezka, mtime, wynik FROM g_gps_geoclip")}
                for gr in gr_reszty:
                    idx = sorted({0, len(gr) // 2, len(gr) - 1})[:GEOCLIP_PROBKI]
                    wyniki = []
                    for i in idx:
                        z = gr[i]
                        if not _ustaw(g, komunikat=f"Rozpoznaję miejsce ze zdjęcia (GeoCLIP): {zrobione + 1} z {probki}…",
                                      zrobione=zrobione, wszystkie=probki):
                            raise InterruptedError
                        zap = pamiec.get(z["sciezka"])
                        if zap and zap[0] == z["mtime"]:
                            w = [tuple(x) for x in json.loads(zap[1])]
                        else:
                            w = geoclip.przewiduj(modele, z["sciezka"], 5)
                            db.execute("INSERT OR REPLACE INTO g_gps_geoclip (sciezka, mtime, wynik) VALUES (?,?,?)",
                                       (z["sciezka"], z["mtime"], json.dumps(w)))
                            db.commit()
                        if w:
                            wyniki.append(w)
                        zrobione += 1
                    if not wyniki:
                        continue
                    alt = polacz_geoclip(wyniki)
                    la, lo, p = alt[0]
                    grupy.append(_grupa_json(gr, "geoclip", f"GeoCLIP — rozpoznanie z obrazu ({'<1' if p < 0.01 else '~' + str(round(p * 100))}%)", "przybliżona",
                                             [[z["id"], la, lo] for z in gr], {"alternatywy": [list(a) for a in alt[1:]], "jeden_punkt": True}))
                    bez -= len(gr)
            finally:
                db.close()
        grupy.sort(key=lambda x: x["od"], reverse=True)
        pods = {"bez_gps": len(zdjecia), "propozycje": sum(x["n"] for x in grupy), "grupy": len(grupy), "bez_propozycji": bez,
                "slady": len(slady_), "zrodla": {t: sum(x["n"] for x in grupy if x["typ"] == t) for t in ("slad", "sasiad", "wizyta", "przejazd", "geoclip")}}
        with _BLOKADA:
            _WYNIKI[k] = {"grupy": grupy, "podsumowanie": pods, "czas": time.time()}
            _STANY[k].update(trwa=False, komunikat=f"Gotowe — propozycje dla {pods['propozycje']} z {len(zdjecia)} zdjęć bez GPS.",
                             zrobione=0, wszystkie=0)
    except InterruptedError:
        with _BLOKADA:
            _STANY[k].update(trwa=False, komunikat="Przerwano.", zrobione=0, wszystkie=0)
    except Exception as e:  # noqa: BLE001 — błąd ma trafić do widoku
        LOG.exception("bez_gps: skan")
        with _BLOKADA:
            _STANY[k].update(trwa=False, blad=f"Skan nie powiódł się: {e}", komunikat="")


# --- przegląd i decyzje ----------------------------------------------------------------------------------------------------
def grupy(g, od: int = 0, ile: int = 40, typ: str = "") -> dict:
    with _BLOKADA:
        w = _WYNIKI.get(str(g.baza)) or {}
        lista = [x for x in w.get("grupy") or [] if not typ or x["typ"] == typ]
    return {"razem": len(lista), "grupy": lista[od:od + ile], "podsumowanie": w.get("podsumowanie")}


def _usun_z_wynikow(g, ids: set) -> None:
    with _BLOKADA:
        w = _WYNIKI.get(str(g.baza))
        if not w:
            return
        nowe = []
        for x in w["grupy"]:
            zostaje = [i for i in x["ids"] if i not in ids]
            if len(zostaje) == len(x["ids"]):
                nowe.append(x)
            elif zostaje:
                x = {**x, "ids": zostaje, "n": len(zostaje), "punkty": [p for p in x["punkty"] if p[0] not in ids],
                     "pliki": [f for f in x.get("pliki", []) if f["id"] not in ids]}
                nowe.append(x)
        w["grupy"] = nowe


def odrzuc(g, ids: list[int], typ: str) -> dict:
    """Ta propozycja (to źródło) dla tych zdjęć nie wróci przy kolejnym skanie; inne źródła — tak."""
    if typ not in ("slad", "sasiad", "wizyta", "przejazd", "geoclip"):
        return {"blad": "nieznane źródło"}
    db = _db(g)
    try:
        sciezki = [r[0] for i in ids[:2000] for r in db.execute("SELECT sciezka FROM pliki WHERE rowid=?", (int(i),))]
        db.executemany("INSERT OR REPLACE INTO g_gps_decyzje (sciezka, zrodlo, czas) VALUES (?,?,?)",
                       [(s, typ, time.time()) for s in sciezki])
        db.commit()
    finally:
        db.close()
    _usun_z_wynikow(g, set(ids))
    return {"ok": True, "odrzucone": len(sciezki)}


def przyjete(g, ids: list[int]) -> dict:
    """Po zapisie lokalizacji (przez /api/g/lokalizacja) — grupa znika z przeglądu."""
    _usun_z_wynikow(g, set(ids))
    return {"ok": True}


def dni_bez_gps(g) -> set[str]:
    zdjecia, _, _ = wczytaj(g)
    return {z["t"].date().isoformat() for z in zdjecia}
