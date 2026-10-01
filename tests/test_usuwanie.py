"""🗑 Usuń: plik trafia do <folder>/Odłożone/Usunięte (z cofaniem) — w galerii, zakładkach projektu i na telefonie."""

import json
import os
import urllib.error
import urllib.request

import pytest

from katalogator import aplikacja, galeria, pilot, planista, skaner, sprzatanie, usuwanie
from test_katalogator import _jpg_z_exif


def _dysk(tmp_path):
    k = tmp_path / "dysk"
    (k / "2023").mkdir(parents=True)
    _jpg_z_exif(k / "2023" / "a.jpg", data="2023:07:11 12:00:00", gps=None)
    _jpg_z_exif(k / "2023" / "b.jpg", data="2023:07:12 12:00:00", gps=None)
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    return k, db


def test_usun_i_cofnij_z_planem(tmp_path):
    k, db = _dysk(tmp_path)
    planista.generuj(db, [{"sciezka": str(k), "tryb": "kopiuj"}], str(tmp_path / "Biblioteka"))
    a = db.execute("SELECT rowid FROM pliki WHERE sciezka LIKE '%a.jpg'").fetchone()[0]
    w = usuwanie.usun(db, [a])
    assert w["usuniete"] == 1 and not (k / "2023" / "a.jpg").exists()
    assert (k / "Odłożone" / "Usunięte" / "2023" / "a.jpg").exists()
    assert db.execute("SELECT pominiety, uwaga FROM plan WHERE sciezka LIKE '%a.jpg'").fetchone()[0] == 1
    assert sprzatanie.odlozone([str(k)])["kategorie"][0]["nazwa"] == "Usunięte"  # do usunięcia na stałe
    c = usuwanie.cofnij(db, w["partia"])
    assert c["przywrocone"] == 1 and (k / "2023" / "a.jpg").exists() and not (k / "Odłożone").exists()
    # ten sam numer pliku (miniatury, propozycja) i z powrotem w propozycji
    assert db.execute("SELECT rowid FROM pliki WHERE sciezka LIKE '%a.jpg'").fetchone()[0] == a
    assert db.execute("SELECT pominiety, uwaga FROM plan WHERE sciezka LIKE '%a.jpg'").fetchone()[:] == (0, None)


def test_galeria_usuwa_tylko_w_swoim_zakresie(tmp_path):
    k, db = _dysk(tmp_path)
    inny = tmp_path / "inny"
    inny.mkdir()
    _jpg_z_exif(inny / "c.jpg", data="2020:01:01 12:00:00", gps=None)
    skaner.skanuj(str(inny), db, wypisz=lambda *_: None)
    g = galeria.Galeria(tmp_path / "k.db", lambda: [str(k)])
    c = db.execute("SELECT rowid FROM pliki WHERE sciezka LIKE '%c.jpg'").fetchone()[0]
    assert "blad" in g.usun([c]) and (inny / "c.jpg").exists()  # spoza zakresu galerii — nie
    ids = [p["id"] for p in g.pliki("2023", None)["pliki"]]
    w = galeria.obsluz_post(g, "/api/g/usun", {"ids": ids})
    assert w["usuniete"] == 2 and g.lata()["razem"] == 0
    assert galeria.obsluz_post(g, "/api/g/usun/cofnij", {"partia": w["partia"]})["przywrocone"] == 2
    assert g.lata()["razem"] == 2


def test_usuwanie_z_telefonu_tylko_ze_sterowaniem(tmp_path):
    k, _ = _dysk(tmp_path)
    stan = aplikacja.Stan(tmp_path / "dane")
    stan.ustawienia["zrodla"] = [{"sciezka": str(k), "tryb": "kopiuj"}]
    stan.rozpocznij_skan()
    import time
    while stan.zajety():
        time.sleep(0.05)
    s = galeria.SerwerGalerii(stan.galeria("wszystko"), port=0, pin="1357", host="127.0.0.1",
                              pilot=pilot.Pilot(stan, sterowanie=False), galerie=stan.galeria).start()
    try:
        b = f"http://127.0.0.1:{s.port}"

        def post(sciezka, dane, t=None):
            r = urllib.request.Request(b + sciezka, data=json.dumps(dane).encode(),
                                       headers={"Content-Type": "application/json", **({"X-Token": t} if t else {})})
            with urllib.request.urlopen(r, timeout=10) as o:
                return json.loads(o.read())
        t = post("/api/g/zaloguj", {"pin": "1357"})["t"]
        g = stan.galeria("wszystko")
        ids = [p["id"] for p in g.pliki("2023", None)["pliki"]]
        with pytest.raises(urllib.error.HTTPError) as e:
            post("/api/g/usun?z=wszystko", {"ids": ids[:1]})
        assert e.value.code == 401
        with pytest.raises(urllib.error.HTTPError) as e:
            post("/api/g/usun?z=wszystko", {"ids": ids[:1]}, t)
        assert e.value.code == 403 and os.path.exists(k / "2023" / "a.jpg")
        s.pilot.sterowanie = True
        w = post("/api/g/usun?z=wszystko", {"ids": ids[:1]}, t)
        assert w["usuniete"] == 1 and len(os.listdir(k / "2023")) == 1
        assert post("/api/g/usun/cofnij?z=wszystko", {"partia": w["partia"]}, t)["przywrocone"] == 1
    finally:
        s.stop()
