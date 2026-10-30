"""✈ Podróże: ślady GPS wypraw ze Stravy i Intervals.icu.

Google Timeline zapisuje dla wielu przejazdów i spacerów tylko początek i koniec, więc na mapie wychodziły proste kreski.
Prawdziwy ślad ma Strava / Intervals.icu — Katalogator pobiera go dla aktywności z dni wypraw, zapamiętuje na komputerze
(`%LOCALAPPDATA%\\Katalogator\\podroze\\slady`) i składa osobny plik na wyprawę (`dane/slady/<id>.json`), który aplikacja
Podróży rysuje na mapie. Klucze dostępu leżą tylko w `podroze/klucze.json` na tym komputerze; do panelu nie wracają,
a program łączy się wyłącznie ze strava.com i intervals.icu. Pobieranie można wznowić — zapamiętane ślady się nie powtarzają.
"""
from __future__ import annotations

import base64
import datetime as dt
import gzip
import json
import logging
import math
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

LOG = logging.getLogger("katalogator.slady")

POLA_KLUCZY = ("strava_client_id", "strava_client_secret", "strava_refresh_token", "intervals_athlete_id", "intervals_api_key")
# nazwy pól w kopii zapasowej aplikacji „Szczyty” (blok settings) i w pliku „Zawody” (blok access)
POLA_Z_KOPII = {"clientId": "strava_client_id", "clientSecret": "strava_client_secret", "refreshToken": "strava_refresh_token",
                "intervalsAthleteId": "intervals_athlete_id", "intervalsApiKey": "intervals_api_key"}
MAKS_PUNKTOW = 900          # punkty jednego śladu w pliku wyprawy
TOLERANCJA_M = 4.0          # uproszczenie śladu (Douglas–Peucker)
WERSJA_PAMIECI = 2          # 2: zapamiętany ślad ma czas (sekundy od startu) — potrzebny do zdjęć bez GPS

_stan = {"trwa": False, "etap": "", "zrobione": 0, "wszystkie": 0, "komunikat": "", "blad": "", "koniec": 0.0}
_blokada = threading.Lock()
_przerwij = threading.Event()


# --- ścieżki, klucze ----------------------------------------------------------------------------------------------------
def _kor(katalog) -> Path:
    return Path(katalog) / "podroze"


def folder_sladow(katalog) -> Path:
    return _kor(katalog) / "slady"


def nazwa_pliku(id_wyprawy) -> str:
    """Nazwa pliku śladów wyprawy — ten sam wzór co w aplikacji (trasa.js)."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(id_wyprawy))[:100]


def _zapisz_json(sciezka: Path, obiekt) -> None:
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    tmp = sciezka.with_name(sciezka.name + ".nowy")
    tmp.write_text(json.dumps(obiekt, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, sciezka)


def klucze(katalog) -> dict:
    try:
        d = json.loads((_kor(katalog) / "klucze.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: str(d[k]).strip() for k in POLA_KLUCZY if d.get(k)} if isinstance(d, dict) else {}


def zapisz_klucze(katalog, nowe: dict) -> None:
    """Zmienia tylko podane pola; pusty ciąg usuwa pole."""
    k = klucze(katalog)
    for n, v in (nowe or {}).items():
        if n in POLA_KLUCZY:
            v = str(v or "").strip()
            if v:
                k[n] = v
            else:
                k.pop(n, None)
    p = _kor(katalog) / "klucze.json"
    _zapisz_json(p, k)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def _etykieta(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", t)


# etykiety z plików tekstowych / arkuszy (np. „Client_secret_strava”, „token_odświeżania_strava”, „intervals_api_key_michal”)
def _pole_z_etykiety(e: str) -> str | None:
    if "intervals" in e and "athlete" in e:
        return "intervals_athlete_id"
    if "intervals" in e and ("apikey" in e or e.endswith("key")):
        return "intervals_api_key"
    if "secret" in e:
        return "strava_client_secret"
    if "refresh" in e or "odswiez" in e:
        return "strava_refresh_token"
    if e in ("clientid", "identyfikatorklienta") or e.startswith(("clientid", "identyfikatorklienta", "stravaclientid")):
        return "strava_client_id"
    return None


def _z_tekstu(tekst: str) -> dict:
    wynik: dict = {}
    for linia in tekst.splitlines():
        czesci = [c.strip().strip('"\'') for c in re.split(r"\t|;|=|:|,", linia, maxsplit=1)]
        if len(czesci) == 2 and czesci[1]:
            pole = _pole_z_etykiety(_etykieta(czesci[0]))
            if pole:
                wynik[pole] = czesci[1]
    return wynik


def klucze_z_kopii(katalog, plik: str) -> dict:
    """Przepisuje klucze z kopii zapasowej aplikacji Szczyty (JSON: blok settings / access) albo z pliku tekstowego / CSV
    z parami „nazwa  wartość” — lokalnie, nic nie jest wyświetlane ani wysyłane."""
    p = Path(str(plik or "").strip().strip('"'))
    if not p.is_file() or p.suffix.lower() not in (".json", ".txt", ".csv", ".tsv", ".md") or p.stat().st_size > 20 * 1048576:
        return {"blad": "Wskaż plik z kluczami: kopię zapasową aplikacji Szczyty (.json) albo plik tekstowy / CSV z parami nazwa–wartość."}
    try:
        tekst = p.read_text(encoding="utf-8-sig")
    except (OSError, ValueError):
        return {"blad": "Nie udało się odczytać tego pliku."}
    nowe: dict = {}
    try:
        d = json.loads(tekst)
    except ValueError:
        d = None
    if isinstance(d, dict):
        blok = next((d[n] for n in ("settings", "access") if isinstance(d.get(n), dict)), d)
        nowe = {POLA_Z_KOPII[n]: blok[n] for n in POLA_Z_KOPII if blok.get(n)}
    if not nowe:
        nowe = _z_tekstu(tekst)
    if not nowe:
        return {"blad": "W tym pliku nie ma kluczy Stravy ani Intervals.icu."}
    zapisz_klucze(katalog, nowe)
    return {"ok": True, "wczytano": len(nowe)}


# --- protokół HTTP (do podmiany w testach) ---------------------------------------------------------------------------------
class BladSieci(Exception):
    def __init__(self, kod: int, tekst: str = ""):
        super().__init__(f"HTTP {kod} {tekst}".strip())
        self.kod = kod


def _http(url: str, naglowki: dict | None = None, dane: dict | None = None, limit: int = 25):
    """GET (albo POST formularza) → obiekt JSON. Kody ≥ 400 → BladSieci."""
    body = urllib.parse.urlencode(dane).encode() if dane is not None else None
    zad = urllib.request.Request(url, data=body, headers={"User-Agent": "Katalogator", **(naglowki or {})})
    try:
        with urllib.request.urlopen(zad, timeout=limit) as r:  # noqa: S310 — adresy tylko strava.com i intervals.icu
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise BladSieci(e.code, e.reason) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise BladSieci(0, str(e)) from None
    except ValueError as e:
        raise BladSieci(-1, "nieczytelna odpowiedź") from e


HTTP = _http


# --- Intervals.icu i Strava ------------------------------------------------------------------------------------------------
def _intervals_naglowek(k: dict) -> dict:
    return {"Authorization": "Basic " + base64.b64encode(f"API_KEY:{k['intervals_api_key']}".encode()).decode()}


def _intervals_lista(k: dict, od: str, do: str) -> list[dict]:
    aid = urllib.parse.quote(k["intervals_athlete_id"], safe="")
    lista = HTTP(f"https://intervals.icu/api/v1/athlete/{aid}/activities?oldest={od}&newest={do}", _intervals_naglowek(k))
    wynik = []
    for a in lista if isinstance(lista, list) else []:
        start = str(a.get("start_date_local") or "")
        if a.get("id") and len(start) >= 10:
            wynik.append({"zrodlo": "intervals", "id": str(a["id"]), "start": start[:19], "nazwa": a.get("name") or "",
                          "typ": a.get("type") or "", "km": round(float(a.get("distance") or 0) / 1000, 2),
                          "strava": str(a.get("strava_id") or "")})
    return wynik


def _intervals_slad(k: dict, id_: str) -> list[list]:
    st = HTTP(f"https://intervals.icu/api/v1/activity/{urllib.parse.quote(id_, safe='')}/streams?types=latlng,altitude,time,distance",
              _intervals_naglowek(k))
    dane = {s.get("type"): s for s in st if isinstance(s, dict)} if isinstance(st, list) else {}
    ll = (dane.get("latlng") or {})
    a, b = ll.get("data") or [], ll.get("data2")
    pary = list(zip(a, b)) if b else [tuple(x) if isinstance(x, (list, tuple)) and len(x) == 2 else (None, None) for x in a]
    wys, dyst = (dane.get("altitude") or {}).get("data") or [], (dane.get("distance") or {}).get("data") or []
    return _punkty(pary, wys, dyst, (dane.get("time") or {}).get("data") or [])


class _Strava:
    def __init__(self, katalog, k: dict):
        self.katalog, self.k, self.token, self.do = katalog, k, "", 0.0

    def naglowek(self) -> dict:
        if not self.token or time.time() > self.do - 60:
            o = HTTP("https://www.strava.com/oauth/token", None,
                     {"client_id": self.k["strava_client_id"], "client_secret": self.k["strava_client_secret"],
                      "refresh_token": self.k["strava_refresh_token"], "grant_type": "refresh_token"})
            self.token, self.do = o.get("access_token") or "", float(o.get("expires_at") or time.time() + 3600)
            if not self.token:
                raise BladSieci(401, "brak tokenu")
            nowy = o.get("refresh_token")
            if nowy and nowy != self.k["strava_refresh_token"]:   # Strava potrafi wydać nowy — stary może przestać działać
                self.k["strava_refresh_token"] = nowy
                zapisz_klucze(self.katalog, {"strava_refresh_token": nowy})
        return {"Authorization": "Bearer " + self.token}

    def lista(self, od: str, do: str) -> list[dict]:
        t0 = int(dt.datetime.strptime(od, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp()) - 86400
        t1 = int(dt.datetime.strptime(do, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp()) + 2 * 86400
        wynik, strona = [], 1
        while strona < 60:
            czesc = HTTP(f"https://www.strava.com/api/v3/athlete/activities?after={t0}&before={t1}&per_page=200&page={strona}", self.naglowek())
            if not isinstance(czesc, list) or not czesc:
                break
            for a in czesc:
                start = str(a.get("start_date_local") or "")
                if a.get("id") and len(start) >= 10 and a.get("start_latlng"):
                    wynik.append({"zrodlo": "strava", "id": str(a["id"]), "start": start[:19], "nazwa": a.get("name") or "",
                                  "typ": a.get("sport_type") or a.get("type") or "", "km": round(float(a.get("distance") or 0) / 1000, 2)})
            if len(czesc) < 200:
                break
            strona += 1
        return wynik

    def slad(self, id_: str) -> list[list]:
        st = HTTP(f"https://www.strava.com/api/v3/activities/{urllib.parse.quote(id_, safe='')}/streams?keys=latlng,altitude,time,distance&key_by_type=true",
                  self.naglowek())
        st = st if isinstance(st, dict) else {}
        return _punkty((st.get("latlng") or {}).get("data") or [], (st.get("altitude") or {}).get("data") or [],
                       (st.get("distance") or {}).get("data") or [], (st.get("time") or {}).get("data") or [])


def _punkty(pary, wys, dyst, czas=()) -> list[list]:
    """[lat, lon, wysokość, dystans, sekundy od startu] — czas służy do dopasowania zdjęć bez GPS (bez_gps.py)."""
    wynik = []
    for i, p in enumerate(pary):
        try:
            la, lo = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            continue
        if not (-90 <= la <= 90 and -180 <= lo <= 180) or (la == 0 and lo == 0):
            continue
        w = wys[i] if i < len(wys) and wys[i] is not None else None
        d = dyst[i] if i < len(dyst) and dyst[i] is not None else None
        t = czas[i] if i < len(czas) and czas[i] is not None else None
        wynik.append([round(la, 6), round(lo, 6), round(w, 1) if w is not None else None, round(d, 1) if d is not None else None,
                      int(t) if t is not None else None])
    return wynik


def przerzedz(pkt: list[list], co_s: int = 10) -> list[list]:
    """Do zapamiętania: punkt co ≥ `co_s` sekund (czas zostaje dokładny do dopasowania zdjęć); bez czasu — uproszczenie kształtu."""
    if len(pkt) < 3 or any(p[4] is None for p in (pkt[0], pkt[-1])):
        return upros(pkt, maks=4000)
    wynik, ost = [pkt[0]], pkt[0][4]
    for p in pkt[1:-1]:
        if p[4] is not None and p[4] - ost >= co_s:
            wynik.append(p)
            ost = p[4]
    wynik.append(pkt[-1])
    return wynik


# --- uproszczenie śladu ----------------------------------------------------------------------------------------------------
def upros(pkt: list[list], tol_m: float = TOLERANCJA_M, maks: int = MAKS_PUNKTOW) -> list[list]:
    """Douglas–Peucker (iteracyjnie) na rzucie płaskim, potem równomierne przerzedzenie do `maks` punktów."""
    n = len(pkt)
    if n <= 2:
        return pkt
    la0 = math.radians(pkt[0][0])
    xy = [(math.radians(p[1]) * 6371000 * math.cos(la0), math.radians(p[0]) * 6371000) for p in pkt]
    zostaje = [False] * n
    zostaje[0] = zostaje[-1] = True
    stos = [(0, n - 1)]
    while stos:
        a, b = stos.pop()
        if b <= a + 1:
            continue
        (ax, ay), (bx, by) = xy[a], xy[b]
        dx, dy = bx - ax, by - ay
        dl = math.hypot(dx, dy)
        naj, idx = -1.0, -1
        for i in range(a + 1, b):
            px, py = xy[i]
            d = math.hypot(px - ax, py - ay) if dl == 0 else abs(dy * (px - ax) - dx * (py - ay)) / dl
            if d > naj:
                naj, idx = d, i
        if naj > tol_m:
            zostaje[idx] = True
            stos += [(a, idx), (idx, b)]
    wynik = [p for p, z in zip(pkt, zostaje) if z]
    if len(wynik) > maks:
        krok = (len(wynik) - 1) / (maks - 1)
        wynik = [wynik[round(i * krok)] for i in range(maks)]
    return wynik


# --- pamięć śladów ---------------------------------------------------------------------------------------------------------
def _indeks(katalog) -> dict:
    try:
        d = json.loads((folder_sladow(katalog) / "indeks.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _plik_sladu(katalog, zrodlo: str, id_: str) -> Path:
    return folder_sladow(katalog) / f"{zrodlo}_{re.sub(r'[^A-Za-z0-9_-]', '_', id_)}.gz"


def _zapisz_slad(katalog, zrodlo: str, id_: str, pkt: list[list]) -> None:
    p = _plik_sladu(katalog, zrodlo, id_)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".nowy")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(pkt, f, separators=(",", ":"))
    os.replace(tmp, p)


def _wczytaj_slad(katalog, zrodlo: str, id_: str) -> list[list]:
    try:
        with gzip.open(_plik_sladu(katalog, zrodlo, id_), "rt", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


# --- wyprawy ---------------------------------------------------------------------------------------------------------------
def _wyprawy(katalog) -> list[dict]:
    from . import podroze
    try:
        d = json.loads((podroze.folder_danych(katalog) / "sample-trips.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    lista = d.get("trips") if isinstance(d, dict) else d
    wynik = []
    for i, t in enumerate(lista if isinstance(lista, list) else []):
        try:
            od, do = str(t.get("startDate") or "")[:10], str(t.get("endDate") or "")[:10]
            dt.date.fromisoformat(od)
            dt.date.fromisoformat(do)
        except (ValueError, AttributeError):
            continue
        wynik.append({"id": str(t.get("id") or f"trip-{i}"), "od": od, "do": do})
    return wynik


def _w_wyprawie(wyprawy: list[dict], dzien: str) -> str | None:
    for w in wyprawy:
        if w["od"] <= dzien <= w["do"]:
            return w["id"]
    return None


def zloz(katalog) -> int:
    """Składa pliki śladów wypraw z pamięci (bez sieci): aktywności z dni wyprawy → dane/slady/<id>.json."""
    from . import podroze
    wyprawy, ind = _wyprawy(katalog), _indeks(katalog)
    cel = podroze.folder_danych(katalog) / "slady"
    grupy: dict[str, list] = {}
    for k, a in ind.items():
        if not a.get("slad"):
            continue
        wid = _w_wyprawie(wyprawy, a["start"][:10])
        if wid:
            pkt = [p[:4] for p in upros(_wczytaj_slad(katalog, a["zrodlo"], a["id"]))]
            if len(pkt) > 1:
                grupy.setdefault(wid, []).append({"id": a["id"], "zrodlo": a["zrodlo"], "nazwa": a["nazwa"], "typ": a["typ"],
                                                  "start": a["start"], "km": a["km"], "pts": pkt})
    if cel.is_dir():
        for f in cel.glob("*.json"):
            f.unlink(missing_ok=True)
    for wid, akt in grupy.items():
        akt.sort(key=lambda x: x["start"])
        _zapisz_json(cel / (nazwa_pliku(wid) + ".json"), {"tripId": wid, "aktywnosci": akt})
    return len(grupy)


def plik_wyprawy(katalog, nazwa: str) -> Path | None:
    """Plik śladów wyprawy dla serwera: wyłącznie `<bezpieczna nazwa>.json` z folderu dane/slady."""
    from . import podroze
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}\.json", nazwa or "") or ".." in nazwa:
        return None
    p = podroze.folder_danych(katalog) / "slady" / nazwa
    return p if p.is_file() else None


# --- pobieranie ------------------------------------------------------------------------------------------------------------
def stan(katalog) -> dict:
    k, ind = klucze(katalog), _indeks(katalog)
    f = folder_sladow(katalog)
    from .podroze import _rozmiar
    mb = _rozmiar(f) / 1048576
    with _blokada:
        s = dict(_stan)
    return {"klucze": {"strava": all(k.get(n) for n in ("strava_client_id", "strava_client_secret", "strava_refresh_token")),
                       "intervals": all(k.get(n) for n in ("intervals_athlete_id", "intervals_api_key"))},
            "aktywnosci": len(ind), "ze_sladem": sum(1 for a in ind.values() if a.get("slad")), "rozmiar_mb": round(mb, 1),
            "pobieranie": s}


def _ustaw(**kw) -> None:
    with _blokada:
        _stan.update(kw)


def aktywnosci_z_czasem(katalog) -> list[dict]:
    """Zapamiętane ślady z czasem (do dopasowania zdjęć): start/koniec (czas lokalny) i punkty (sekundy od startu, lat, lon)."""
    wynik = []
    for a in _indeks(katalog).values():
        if not a.get("slad") or a.get("wersja") != WERSJA_PAMIECI:
            continue
        pkt = [(p[4], p[0], p[1]) for p in _wczytaj_slad(katalog, a["zrodlo"], a["id"]) if len(p) > 4 and p[4] is not None]
        if len(pkt) < 2:
            continue
        try:
            start = dt.datetime.fromisoformat(a["start"][:19])
        except ValueError:
            continue
        wynik.append({"zrodlo": a["zrodlo"], "id": a["id"], "nazwa": a.get("nazwa") or "", "typ": a.get("typ") or "",
                      "start": start, "koniec": start + dt.timedelta(seconds=pkt[-1][0]), "pts": pkt})
    return sorted(wynik, key=lambda x: x["start"])


def pobierz(katalog, dni=None) -> dict:
    """Pobiera ślady aktywności z dni wypraw — albo z podanych dni (`dni`: zbiór 'RRRR-MM-DD', np. dni zdjęć bez GPS)."""
    k = klucze(katalog)
    ma_i = bool(k.get("intervals_athlete_id") and k.get("intervals_api_key"))
    ma_s = all(k.get(n) for n in ("strava_client_id", "strava_client_secret", "strava_refresh_token"))
    if not (ma_i or ma_s):
        return {"blad": "Najpierw wpisz klucze Intervals.icu albo Stravy (lub wczytaj je z kopii aplikacji Szczyty)."}
    if not dni and not _wyprawy(katalog):
        return {"blad": "Najpierw zaimportuj dane wypraw — ślady pobieram dla dni, w których były wyprawy."}
    with _blokada:
        if _stan["trwa"]:
            return {"blad": "Pobieranie już trwa."}
        _stan.update(trwa=True, etap="lista", zrobione=0, wszystkie=0, blad="",
                     komunikat="Sprawdzam aktywności z dni zdjęć bez GPS…" if dni else "Sprawdzam aktywności z dni wypraw…")
    _przerwij.clear()
    threading.Thread(target=_pobierz, args=(Path(katalog), k, ma_i, ma_s, set(dni or ())), daemon=True, name="podroze-slady").start()
    return {"ok": True}


def przerwij() -> None:
    _przerwij.set()


def _pobierz(katalog: Path, k: dict, ma_i: bool, ma_s: bool, dni: set | None = None) -> None:
    ind: dict = {}
    try:
        wyprawy = [] if dni else _wyprawy(katalog)
        nalezy = (lambda d: d in dni) if dni else (lambda d: bool(_w_wyprawie(wyprawy, d)))
        od, do = (min(dni), max(dni)) if dni else (min(w["od"] for w in wyprawy), max(w["do"] for w in wyprawy))
        ind = _indeks(katalog)
        kandydaci: list[dict] = []
        uwagi: list[str] = []
        strava = _Strava(katalog, k) if ma_s else None
        if ma_i:
            try:
                kandydaci += _intervals_lista(k, od, do)
            except BladSieci as e:
                uwagi.append(f"Intervals.icu: {_opis_bledu(e)}")
        if strava:
            try:
                kandydaci += strava.lista(od, do)
            except BladSieci as e:
                uwagi.append(f"Strava: {_opis_bledu(e)}")
        # tylko aktywności z dni wypraw; ta sama aktywność w obu źródłach (start w odstępie do 3 min) liczy się raz
        wybrane: list[dict] = []
        for a in sorted(kandydaci, key=lambda x: (x["start"], x["zrodlo"] != "intervals")):
            if not nalezy(a["start"][:10]):
                continue
            dubl = next((b for b in wybrane if abs((dt.datetime.fromisoformat(a["start"]) - dt.datetime.fromisoformat(b["start"])).total_seconds()) <= 180
                         and b.get("alt") is None and b["zrodlo"] != a["zrodlo"]), None)
            if dubl:
                dubl["alt"] = a
            else:
                wybrane.append(a)
        _ustaw(etap="slady", wszystkie=len(wybrane), komunikat=f"Pobieram ślady: {len(wybrane)} aktywności…")
        pobrane = 0
        for i, a in enumerate(wybrane, 1):
            if _przerwij.is_set():
                uwagi.append("Przerwano — zapamiętane ślady zostają.")
                break
            _ustaw(zrobione=i - 1, komunikat=f"Ślad {i} z {len(wybrane)}: {a['nazwa'] or a['start'][:10]}")
            warianty = [a] + ([a["alt"]] if a.get("alt") else [])
            if any(f"{w['zrodlo']}:{w['id']}" in ind and (not ind[f"{w['zrodlo']}:{w['id']}"].get("slad")
                                                          or ind[f"{w['zrodlo']}:{w['id']}"].get("wersja") == WERSJA_PAMIECI) for w in warianty):
                continue   # już sprawdzone (bez śladu albo ze śladem z czasem); ślady sprzed 1.53 pobieramy raz jeszcze — z czasem
            wpis = None
            for w in warianty:
                try:
                    pkt = _intervals_slad(k, w["id"]) if w["zrodlo"] == "intervals" else (strava.slad(w["id"]) if strava else [])
                except BladSieci as e:
                    if e.kod not in (400, 404, 422):   # „brak strumienia GPS” to zwykła aktywność bez śladu; reszta (sieć, limit, klucz) przerywa
                        raise
                    pkt = []
                if len(pkt) > 1:
                    pkt = przerzedz(pkt)
                    _zapisz_slad(katalog, w["zrodlo"], w["id"], pkt)
                    wpis = {**{n: w[n] for n in ("zrodlo", "id", "start", "nazwa", "typ", "km")}, "slad": True, "punkty": len(pkt),
                            "wersja": WERSJA_PAMIECI}
                    pobrane += 1
                    break
            if wpis is None:
                w = a
                wpis = {**{n: w[n] for n in ("zrodlo", "id", "start", "nazwa", "typ", "km")}, "slad": False, "punkty": 0}
            ind[f"{wpis['zrodlo']}:{wpis['id']}"] = wpis
            if i % 10 == 0:
                _zapisz_json(folder_sladow(katalog) / "indeks.json", ind)
        _zapisz_json(folder_sladow(katalog) / "indeks.json", ind)
        n = zloz(katalog)
        txt = f"Gotowe — nowych śladów: {pobrane}, wypraw ze śladami: {n}."
        _ustaw(trwa=False, koniec=time.time(), zrobione=len(wybrane), komunikat=txt + (" " + " ".join(uwagi) if uwagi else ""))
    except BladSieci as e:
        if ind:
            _zapisz_json(folder_sladow(katalog) / "indeks.json", ind)
            zloz(katalog)
        if e.kod == 429:
            msg = "Strava ograniczyła liczbę zapytań. Poczekaj ok. 15 minut i wciśnij „Pobierz” ponownie — pobrane ślady są zapamiętane."
        else:
            msg = f"Pobieranie przerwane: {_opis_bledu(e)}"
        _ustaw(trwa=False, blad=msg, komunikat="")
    except Exception as e:  # noqa: BLE001 — wątek tła: błąd ma trafić do panelu, nie zginąć
        LOG.exception("Podróże: błąd pobierania śladów")
        _ustaw(trwa=False, blad=f"Pobieranie nie powiodło się: {e}", komunikat="")


def _opis_bledu(e: BladSieci) -> str:
    if e.kod in (401, 403):
        return "klucz odrzucony (sprawdź go w ustawieniach)"
    if e.kod == 429:
        return "limit zapytań — spróbuj za kilkanaście minut"
    if e.kod == 0:
        return "brak połączenia z internetem"
    return str(e)


def usun(katalog) -> dict:
    from . import podroze
    with _blokada:
        if _stan["trwa"]:
            return {"blad": "Poczekaj, aż skończy się pobieranie."}
    import shutil
    shutil.rmtree(folder_sladow(katalog), ignore_errors=True)
    shutil.rmtree(podroze.folder_danych(katalog) / "slady", ignore_errors=True)
    _ustaw(zrobione=0, wszystkie=0, komunikat="", blad="")
    return {"ok": True}
