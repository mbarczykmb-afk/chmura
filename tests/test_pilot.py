"""Pilot na telefonie: stan pracy programu, kolejne kroki, przerywanie — po PIN-ie."""

import json
import time
import urllib.error
import urllib.request

import pytest

from katalogator import aplikacja, galeria, pilot
from test_katalogator import _jpg_z_exif


def _serwer(stan, sterowanie=True):
    return galeria.SerwerGalerii(stan.galeria("wszystko"), port=0, pin="1357", host="127.0.0.1",
                                 pilot=pilot.Pilot(stan, sterowanie), galerie=stan.galeria).start()


def _klient(s):
    b = f"http://127.0.0.1:{s.port}"

    def zapytaj(sciezka, dane=None, token=None):
        r = urllib.request.Request(b + sciezka, data=None if dane is None else json.dumps(dane).encode(),
                                   headers={"Content-Type": "application/json", **({"X-Token": token} if token else {})})
        with urllib.request.urlopen(r, timeout=10) as o:
            tresc = o.read()
            return json.loads(tresc) if o.headers.get("Content-Type", "").startswith("application/json") else tresc
    return zapytaj


def _czekaj(stan, limit=30):
    t0 = time.time()
    while stan.zajety() and time.time() - t0 < limit:
        time.sleep(0.05)
    assert not stan.zajety()


def test_pilot_kroki_i_sterowanie(tmp_path):
    zr = tmp_path / "zdjecia"
    zr.mkdir()
    _jpg_z_exif(zr / "a.jpg", data="2021:05:01 10:00:00", gps=None)
    (zr / "b.jpg").write_bytes((zr / "a.jpg").read_bytes())
    stan = aplikacja.Stan(tmp_path / "dane")
    stan.ustawienia["zrodla"] = [{"sciezka": str(zr), "tryb": "kopiuj"}]
    s = _serwer(stan)
    try:
        q = _klient(s)
        assert b"pilot.js" in q("/")  # strona główna na telefonie to pilot
        with pytest.raises(urllib.error.HTTPError) as e:
            q("/api/pilot")
        assert e.value.code == 401
        with pytest.raises(urllib.error.HTTPError) as e:
            q("/api/pilot/skan", {})
        assert e.value.code == 401
        t = q("/api/g/zaloguj", {"pin": "1357"})["t"]
        st = q("/api/pilot", token=t)
        assert [k["klucz"] for k in st["kroki"]] == ["skan", "dup", "analiza", "plan", "wykonanie"]
        assert st["kroki"][0].get("nastepny") and not st["biezace"] and st["sterowanie"]
        q("/api/pilot/skan", {}, token=t)
        _czekaj(stan)
        q("/api/pilot/dup", {}, token=t)
        _czekaj(stan)
        stan._podsumowania = (-1, {})
        st = q("/api/pilot", token=t)
        kroki = {k["klucz"]: k for k in st["kroki"]}
        assert kroki["skan"]["zrobiony"] and kroki["dup"]["zrobiony"] and "1 zbędnych" in kroki["dup"]["opis"]
        assert not kroki["plan"]["dostepny"]  # bez miejsca docelowego — ustawia się na komputerze
        # galeria z wybranym zakresem
        assert q("/api/g/lata?z=wszystko", token=t)["razem"] == 2
        # kroki zmieniające pliki wymagają potwierdzenia; nieznane kroki odrzucane
        with pytest.raises(urllib.error.HTTPError) as e:
            q("/api/pilot/rm", {}, token=t)
        assert e.value.code == 400
        # sterowanie wyłączone: tylko podgląd
        s.pilot.sterowanie = False
        with pytest.raises(urllib.error.HTTPError) as e:
            q("/api/pilot/analiza", {}, token=t)
        assert "wyłączone" in json.loads(e.value.read())["blad"]
        assert q("/api/pilot", token=t)["sterowanie"] is False
    finally:
        s.stop()


def test_pilot_potwierdzenie_i_sprzatanie(tmp_path):
    stan = aplikacja.Stan(tmp_path / "dane")
    assert stan.przelacz_tryb("sprzatanie") is None
    p = pilot.Pilot(stan)
    assert [k["klucz"] for k in p.status()["kroki"]] == ["skan", "dup", "analiza", "usuwanie"]
    assert "Potwierdź" in p.akcja("usuwanie", {})
    assert p.akcja("wykonanie", {"potwierdzam": True}) == "Nieznany krok."  # nie w trybie Sprzątanie
    # przełączenie projektu z telefonu
    porz = next(x["id"] for x in p.status()["projekty"] if x["typ"] == "porzadkowanie")
    assert p.akcja("projekt", {"id": porz}) is None and stan.pid == porz
