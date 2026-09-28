import json
import time

import pytest
from urllib.parse import quote

from test_aplikacja import app  # noqa: F401
from test_planista import swiat  # noqa: F401


def _czekaj(api, klucz):
    for _ in range(200):
        s = json.loads(api("/api/stan")[1])
        z = s["zad"][klucz] if klucz in s["zad"] else s[klucz]
        if not z["trwa"]:
            return s
        time.sleep(0.05)
    raise AssertionError("zadanie nie skończyło się")


def test_pelny_przebieg(app, swiat):  # noqa: F811
    api, _, stan = app
    k, cel, db = swiat
    api("/api/ustawienia", {"zrodla": [{"sciezka": str(k / "Telefon"), "tryb": "kopiuj"},
                                       {"sciezka": str(k / "Praca"), "tryb": "przenies"}], "cel": str(cel)})
    api("/api/skanuj", {})
    _czekaj(api, "skan")
    api("/api/analiza/start", {})
    s = _czekaj(api, "analiza")
    assert s["zad"]["analiza"]["blad"] == "" and s["analiza"]["zdjecia"] >= 11
    api("/api/plan/generuj", {})
    s = _czekaj(api, "plan")
    assert s["zad"]["plan"]["blad"] == "", s["zad"]["plan"]
    assert s["plan"]["kopiuj"] >= 10 and s["plan"]["przenies"] == 1
    d = json.loads(api("/api/plan/drzewo")[1])
    foldery = {f["sciezka"] for f in d["foldery"]}
    assert "Zdjęcia/Zdjęcia z 2023/Lipiec na Helu" in foldery and "Praca" in foldery
    p = json.loads(api("/api/plan/pliki?folder=" + quote("Zdjęcia/Zdjęcia z 2023/Lipiec na Helu"))[1])
    assert p["razem"] == 4  # 3 zdjęcia z GPS + 1 bez (film trafia do Filmy/)
    w = json.loads(api("/api/plan/zmien-nazwe", {"stara": "Praca", "nowa": "Dokumenty firmowe"})[1])
    assert w["zmienione"] == 1
    assert json.loads(api("/api/plan/cofnij", {})[1])["zmienione"] == 1
    assert json.loads(api("/api/plan/ponow", {})[1])["zmienione"] == 1
    spr = json.loads(api("/api/plan/sprawdz")[1])
    assert spr["starczy"] and spr["plikow"] >= 11
    api("/api/wykonaj", {"usun_puste": True})
    s = _czekaj(api, "wykonanie")
    assert s["zad"]["wykonanie"]["blad"] == "", s["zad"]["wykonanie"]
    assert (cel / "Dokumenty firmowe" / "umowa.pdf").exists() and not (k / "Praca" / "umowa.pdf").exists()
    assert s["wykonanie"]["n"] >= 11
    api("/api/wykonanie/cofnij", {})
    s = _czekaj(api, "wykonanie")
    assert (k / "Praca" / "umowa.pdf").exists() and not (cel / "Dokumenty firmowe").exists()


def test_skrypty_ui_bez_tokenu(app):
    api, url, _ = app
    import urllib.request
    baza = url.split("/?")[0]
    for plik in ("plan.js", "analiza.js", "projekt.js", "pomoc.js", "ikona.png"):
        with urllib.request.urlopen(f"{baza}/ui/{plik}", timeout=5) as r:
            assert r.status == 200


def test_film_z_zakresem(app, tmp_path):  # noqa: F811
    api, url, stan = app
    import urllib.request
    from test_katalogator import _mp4
    from datetime import datetime, timezone
    k = tmp_path / "f"; k.mkdir()
    _mp4(k / "VID_1.mp4", datetime(2022, 1, 1, tzinfo=timezone.utc))
    api("/api/ustawienia", {"zrodla": [str(k)]})
    api("/api/skanuj", {})
    _czekaj(api, "skan")
    fid = stan.z_db(lambda db: db.execute("SELECT rowid FROM pliki WHERE rodzaj='film'").fetchone()[0])
    baza, token = url.split("/?t=")
    req = urllib.request.Request(f"{baza}/plik?t={token}&id={fid}", headers={"Range": "bytes=4-11"})
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 206 and r.headers["Content-Range"].endswith("/" + str((k / "VID_1.mp4").stat().st_size))
        assert r.read() == (k / "VID_1.mp4").read_bytes()[4:12]
    import urllib.error
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(f"{baza}/plik?t={token}&id=999999", timeout=5)
    assert e.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as e:  # bez tokenu
        urllib.request.urlopen(f"{baza}/plik?id={fid}", timeout=5)
    assert e.value.code == 403
