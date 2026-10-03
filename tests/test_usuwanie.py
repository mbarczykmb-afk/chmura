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


def test_przejrzane_grupy_znikaja(tmp_path):
    from katalogator import duplikaty
    k = tmp_path / "d"
    k.mkdir()
    for i in range(3):
        for j in range(2):
            (k / f"p{i}_{j}.bin").write_bytes(bytes([i]) * (1000 + i))
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    duplikaty.szukaj(db)
    g = duplikaty.grupy(db, None, 0, 10)
    assert len(g) == 3 and duplikaty.podsumowanie(db)["nadmiar"] == 3
    duplikaty.oznacz_przejrzane(db, "dup", [g[0]["h"]])
    assert [x["h"] for x in duplikaty.grupy(db, None, 0, 10)] == [g[1]["h"], g[2]["h"]]  # bez starej pamięci listy
    assert duplikaty.podsumowanie(db)["nadmiar"] == 2 and duplikaty.ile_przejrzanych(db, "dup") == 1
    duplikaty.oznacz_przejrzane(db, "dup", [], False)  # „pokaż przejrzane”
    assert len(duplikaty.grupy(db, None, 0, 10)) == 3


def test_od_razu_na_stale_tylko_ta_partia(tmp_path):
    from katalogator import duplikaty
    k = tmp_path / "d"
    k.mkdir()
    for i in range(2):
        for j in range(2):
            (k / f"p{i}_{j}.bin").write_bytes(bytes([i]) * (1000 + i))
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    duplikaty.szukaj(db)
    g = duplikaty.grupy(db, None, 0, 10)
    dec = [{"zostaw": x["zostaw"], "usun": [p["id"] for p in x["pliki"] if p["id"] != x["zostaw"]]} for x in g]
    duplikaty.przenies(db, dec[:1])                     # do kosza (zostaje)
    w = duplikaty.przenies(db, dec[1:])                 # „od razu na stałe”
    r = sprzatanie.usun_partie(db, w["partia"])
    assert r["usuniete"] == 1
    assert sprzatanie.odlozone([str(k)])["plikow"] == 1  # wcześniejsza partia nadal w koszu
    assert len([f for f in os.listdir(k) if f.endswith(".bin")]) == 2  # oryginały zostały


def test_pamiec_grup_po_odlozeniu_jak_pelne_przeliczenie(tmp_path):
    from katalogator import duplikaty
    k = tmp_path / "d"
    k.mkdir()
    for i in range(5):
        for j in range(3):
            (k / f"p{i}_{j}.bin").write_bytes(bytes([i]) * (1000 + i))
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    duplikaty.szukaj(db)

    def pelne():
        duplikaty._PAMIEC_GRUP.clear()
        return duplikaty.podsumowanie(db), [(g["h"], g["n"]) for g in duplikaty.grupy(db, None, 0, 50)]

    def z_pamieci():
        return duplikaty.podsumowanie(db), [(g["h"], g["n"]) for g in duplikaty.grupy(db, None, 0, 50)]
    g = duplikaty.grupy(db, None, 0, 50)
    w = duplikaty.przenies(db, [{"zostaw": g[0]["zostaw"], "usun": [p["id"] for p in g[0]["pliki"] if p["id"] != g[0]["zostaw"]]}])
    assert duplikaty._aktualna_pamiec(db)  # poprawiona, nie liczona od nowa
    a = z_pamieci()
    assert a == pelne() and a[0]["grupy"] == 4
    duplikaty.grupy(db, None, 0, 50)
    duplikaty.odloz(db, [g[1]["pliki"][2]["id"]], "usuniete")  # z grupy 3 kopii zostają 2
    a = z_pamieci()
    assert a == pelne() and dict(a[1])[g[1]["h"]] == 2
    duplikaty.grupy(db, None, 0, 50)
    duplikaty.cofnij(db, w["partia"])
    a = z_pamieci()
    assert a == pelne() and a[0]["grupy"] == 5


def test_odkladanie_nie_blokuje_bazy(tmp_path, monkeypatch):
    """W trakcie odkładania wielu plików (po sieci — minuty) inne połączenie może zapisywać decyzje."""
    import os
    import sqlite3
    from katalogator import duplikaty, skaner
    k = tmp_path / "dysk"
    k.mkdir()
    for i in range(3):
        (k / f"p{i}.jpg").write_bytes(b"x" * (100 + i))
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    duplikaty.przygotuj(db)
    ids = [r[0] for r in db.execute("SELECT rowid FROM pliki")]
    inne = sqlite3.connect(str(tmp_path / "k.db"), timeout=0.2)
    zapisy = []
    prawdziwy = os.rename

    def wolny_rename(a, b):  # w trakcie przenoszenia kolejnego pliku ktoś klika decyzję w oknie
        if zapisy is not None and len(zapisy) < 3 and "p0" not in a:
            inne.execute("CREATE TABLE IF NOT EXISTS t (x)")
            inne.execute("INSERT INTO t VALUES (1)")
            inne.commit()
            zapisy.append(a)
        prawdziwy(a, b)
    monkeypatch.setattr(os, "rename", wolny_rename)
    w = duplikaty.odloz(db, ids, "podobne")
    assert w["przeniesione"] == 3 and len(zapisy) == 2
