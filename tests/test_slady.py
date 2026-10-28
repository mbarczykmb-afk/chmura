"""✈ Podróże: ślady GPS wypraw ze Stravy / Intervals.icu (zapytania sieciowe są podmieniane atrapą)."""
import json
import time
from pathlib import Path

import pytest

from katalogator import podroze, slady

TRIPS = {"trips": [{"id": "trip-2025-08-01-0", "title": "Tatry", "startDate": "2025-08-01", "endDate": "2025-08-03", "days": []},
                   {"id": "t2", "title": "Madera", "startDate": "2025-12-14", "endDate": "2025-12-20", "days": []}]}


def _trasa(n=60, la=49.2, lo=20.0):
    return [[la + i * 0.001, lo + i * 0.0015] for i in range(n)]


class Atrapa:
    """Udaje strava.com i intervals.icu; zapamiętuje, o co pytano."""
    def __init__(self):
        self.zapytania = []
        self.bez_sladu = set()
        self.limit_stravy = False

    def __call__(self, url, naglowki=None, dane=None, limit=25):
        self.zapytania.append(url)
        if "oauth/token" in url:
            assert dane["refresh_token"] == "r-stary"
            return {"access_token": "AT", "refresh_token": "r-nowy", "expires_at": time.time() + 3600}
        if "intervals.icu" in url and "/activities?" in url:
            assert naglowki["Authorization"].startswith("Basic ")
            return [{"id": "i100", "start_date_local": "2025-08-01T09:00:00", "name": "Morskie Oko", "type": "Hike", "distance": 18000},
                    {"id": "i101", "start_date_local": "2025-08-02T09:00:00", "name": "Z Stravy", "type": "Run", "distance": 5000},
                    {"id": "i999", "start_date_local": "2025-09-10T09:00:00", "name": "Poza wyprawą", "type": "Run", "distance": 1000}]
        if "intervals.icu" in url and "/streams" in url:
            if "i100" in url:
                return [{"type": "latlng", "data": _trasa(), "data2": None}, {"type": "altitude", "data": [900 + i for i in range(60)]},
                        {"type": "distance", "data": [i * 50.0 for i in range(60)]}]
            return [{"type": "latlng", "data": []}]   # aktywność ze Stravy: Intervals nie oddaje śladu
        if "strava.com" in url and "athlete/activities" in url:
            assert naglowki["Authorization"] == "Bearer AT"
            if self.limit_stravy:
                raise slady.BladSieci(429)
            return [{"id": 777, "start_date_local": "2025-08-02T09:00:30Z", "name": "Z Stravy", "sport_type": "Run", "distance": 5000, "start_latlng": [49.3, 20.1]},
                    {"id": 778, "start_date_local": "2025-08-03T07:00:00Z", "name": "Bez GPS", "sport_type": "Workout", "distance": 100, "start_latlng": []}]
        if "strava.com" in url and "/streams" in url:
            return {"latlng": {"data": _trasa(40, 49.3, 20.1)}, "altitude": {"data": [1000.0] * 40}, "distance": {"data": [i * 10.0 for i in range(40)]}}
        raise AssertionError("nieoczekiwane zapytanie: " + url)


@pytest.fixture
def kat(tmp_path, monkeypatch):
    d = podroze.folder_danych(tmp_path)
    d.mkdir(parents=True)
    (d / "sample-trips.json").write_text(json.dumps(TRIPS), encoding="utf-8")
    at = Atrapa()
    monkeypatch.setattr(slady, "HTTP", at)
    slady._stan.update(trwa=False, komunikat="", blad="")
    slady.zapisz_klucze(tmp_path, {"intervals_athlete_id": "i1", "intervals_api_key": "KLUCZ",
                                   "strava_client_id": "1", "strava_client_secret": "s", "strava_refresh_token": "r-stary"})
    return tmp_path, at


def _czekaj():
    t0 = time.time()
    while slady._stan["trwa"] and time.time() - t0 < 15:
        time.sleep(0.02)
    assert not slady._stan["trwa"]


def test_uproszczenie_zachowuje_zakret():
    prosta = [[50 + i * 1e-4, 20.0] for i in range(100)]
    assert len(slady.upros(prosta)) == 2
    zakret = prosta + [[50.0099, 20.0 + i * 1e-4] for i in range(1, 100)]
    u = slady.upros(zakret)
    assert 3 <= len(u) < 10 and [50.0099, 20.0] in [[round(p[0], 4), round(p[1], 4)] for p in u]
    assert len(slady.upros([[50 + i * 1e-3, 20 + (i % 7) * 1e-3] for i in range(5000)], 0.0, 300)) == 300


def test_klucze_zapis_odczyt_i_kopia(tmp_path):
    slady.zapisz_klucze(tmp_path, {"intervals_api_key": " abc ", "nieznane": "x"})
    assert slady.klucze(tmp_path) == {"intervals_api_key": "abc"}
    slady.zapisz_klucze(tmp_path, {"intervals_api_key": ""})
    assert slady.klucze(tmp_path) == {}
    kopia = tmp_path / "kopia.json"
    kopia.write_text(json.dumps({"ascents": [], "settings": {"clientId": "9", "clientSecret": "s", "refreshToken": "r", "intervalsApiKey": "k",
                                                              "intervalsAthleteId": "i5", "trailM": 25}}), encoding="utf-8")
    assert slady.klucze_z_kopii(tmp_path, str(kopia)) == {"ok": True, "wczytano": 5}
    assert slady.klucze(tmp_path)["strava_refresh_token"] == "r"
    zawody = tmp_path / "zawody.json"
    zawody.write_text(json.dumps({"access": {"intervalsApiKey": "k2"}}), encoding="utf-8")
    assert slady.klucze_z_kopii(tmp_path, str(zawody))["wczytano"] == 1
    assert "blad" in slady.klucze_z_kopii(tmp_path, str(tmp_path / "nie-ma.json"))
    (tmp_path / "puste.json").write_text("{}", encoding="utf-8")
    assert "blad" in slady.klucze_z_kopii(tmp_path, str(tmp_path / "puste.json"))


def test_pobieranie_sladow_dla_dni_wypraw(kat):
    tmp, at = kat
    assert slady.pobierz(tmp) == {"ok": True}
    _czekaj()
    s = slady.stan(tmp)
    assert not s["pobieranie"]["blad"], s["pobieranie"]
    assert s["aktywnosci"] == 2 and s["ze_sladem"] == 2        # poza wyprawą i bez GPS — nie pobieramy
    assert slady.klucze(tmp)["strava_refresh_token"] == "r-nowy"   # nowy token Stravy zapamiętany
    p = slady.plik_wyprawy(tmp, "trip-2025-08-01-0.json")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert [a["nazwa"] for a in d["aktywnosci"]] == ["Morskie Oko", "Z Stravy"]
    assert d["aktywnosci"][0]["zrodlo"] == "intervals" and d["aktywnosci"][1]["zrodlo"] == "strava"   # Intervals bez śladu → Strava
    assert len(d["aktywnosci"][0]["pts"]) >= 2 and d["aktywnosci"][0]["pts"][0][2] == 900
    assert slady.plik_wyprawy(tmp, "t2.json") is None
    # drugi raz nie pytamy już o ślady (wznawianie), a wyniki zostają
    n = len([u for u in at.zapytania if "/streams" in u])
    assert slady.pobierz(tmp) == {"ok": True}
    _czekaj()
    assert len([u for u in at.zapytania if "/streams" in u]) == n
    assert slady.stan(tmp)["ze_sladem"] == 2


def test_limit_stravy_nie_traci_pobranego(kat):
    tmp, at = kat
    at.limit_stravy = True
    slady.pobierz(tmp)
    _czekaj()
    s = slady.stan(tmp)["pobieranie"]
    assert not s["blad"]            # lista Stravy jest dodatkiem — Intervals i tak coś zwróciło
    assert "Strava" in s["komunikat"] and slady.stan(tmp)["ze_sladem"] == 1


def test_bez_kluczy_lub_wypraw(tmp_path):
    assert "klucze" in slady.pobierz(tmp_path)["blad"]
    slady.zapisz_klucze(tmp_path, {"intervals_athlete_id": "i1", "intervals_api_key": "k"})
    assert "zaimportuj" in slady.pobierz(tmp_path)["blad"]


def test_plik_wyprawy_tylko_bezpieczne_nazwy(kat):
    tmp, _ = kat
    cel = podroze.folder_danych(tmp) / "slady"
    cel.mkdir()
    (cel / "ok.json").write_text("{}", encoding="utf-8")
    (podroze.folder_danych(tmp) / "sekret.json").write_text("{}", encoding="utf-8")
    assert slady.plik_wyprawy(tmp, "ok.json") == cel / "ok.json"
    for zla in ("../sekret.json", "..%2Fsekret.json", "a/b.json", "ok.txt", "", "..json", "ok.json\x00.txt"):
        assert slady.plik_wyprawy(tmp, zla) is None, zla
    assert slady.nazwa_pliku("trip/2025:08") == "trip_2025_08"


def test_usuniecie(kat):
    tmp, _ = kat
    slady.pobierz(tmp)
    _czekaj()
    assert slady.usun(tmp) == {"ok": True}
    assert slady.stan(tmp)["aktywnosci"] == 0 and slady.plik_wyprawy(tmp, "trip-2025-08-01-0.json") is None
    assert slady.klucze(tmp)            # klucze zostają — usuwa się je osobno
