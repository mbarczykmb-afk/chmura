"""Tryb Sprzątanie: duplikaty i śmieci odkładane na miejscu, potem usuwane na stałe — bez kopiowania i drzewa."""

import os

from katalogator import aplikacja, duplikaty, skaner, sprzatanie
from test_katalogator import _jpg_z_exif


def _dysk(tmp_path):
    k = tmp_path / "dysk"
    (k / "Wakacje").mkdir(parents=True)
    (k / "Stare" / "thumbnails").mkdir(parents=True)
    _jpg_z_exif(k / "Wakacje" / "IMG_1.jpg", data="2023:07:11 12:00:00", gps=None)
    _jpg_z_exif(k / "Wakacje" / "IMG_2.jpg", data="2023:07:12 12:00:00", gps=None)
    (k / "Stare" / "IMG_1 kopia.jpg").write_bytes((k / "Wakacje" / "IMG_1.jpg").read_bytes())  # duplikat
    (k / "Stare" / "pusty.txt").write_bytes(b"")
    (k / "Stare" / "pobieranie.crdownload").write_bytes(b"x" * 100)
    (k / "Stare" / "thumbnails" / "t1.jpg").write_bytes(b"\xff\xd8" + b"x" * 50)
    return k


def test_smieci_odlozone_i_usuniete_na_stale(tmp_path):
    k = _dysk(tmp_path)
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    smieci = {os.path.basename(p["sciezka"]): p["powod"] for p in sprzatanie.lista_smieci(db)}
    assert set(smieci) == {"pusty.txt", "pobieranie.crdownload", "t1.jpg"}
    assert "IMG_1.jpg" not in smieci and "IMG_2.jpg" not in smieci
    # duplikaty: kopia do Odłożone/Duplikaty, oryginał zostaje
    duplikaty.szukaj(db)
    g = duplikaty.grupy(db, None, 0, 10)[0]
    duplikaty.przenies(db, [{"zostaw": g["zostaw"], "usun": [p["id"] for p in g["pliki"] if p["id"] != g["zostaw"]]}])
    # śmieci: do Odłożone/Śmieci
    w = duplikaty.odloz(db, [p["id"] for p in sprzatanie.lista_smieci(db)], "smieci")
    assert w["przeniesione"] == 3
    o = sprzatanie.odlozone([str(k)])
    assert {x["nazwa"]: x["plikow"] for x in o["kategorie"]} == {"Duplikaty": 1, "Śmieci": 3}
    # tylko śmieci na stałe; duplikaty jeszcze do przejrzenia
    r = sprzatanie.usun_odlozone(db, [str(k)], ["Śmieci"])
    assert r["usuniete"] == 3 and not r["bledy"]
    assert not (k / "Odłożone" / "Śmieci").exists() and (k / "Odłożone" / "Duplikaty").exists()
    sprzatanie.usun_odlozone(db, [str(k)])
    assert not (k / "Odłożone").exists()
    assert (k / "Wakacje" / "IMG_1.jpg").exists() and (k / "Wakacje" / "IMG_2.jpg").exists()  # oryginały zostają
    assert db.execute("SELECT COUNT(*) FROM operacje").fetchone()[0] == 0  # nie ma czego „cofać”
    # puste foldery po sprzątaniu (Stare/thumbnails, Stare) znikają, wybrany folder zostaje
    assert sprzatanie.usun_puste_foldery([str(k)]) == 2
    assert not (k / "Stare").exists() and k.exists() and (k / "Wakacje").exists()


def test_usuwanie_tylko_w_odlozonych(tmp_path):
    k = tmp_path / "dysk"
    (k / "Odłożone" / "Duplikaty").mkdir(parents=True)
    (k / "Odłożone" / "Duplikaty" / "a.jpg").write_bytes(b"x")
    (k / "Ważne").mkdir()
    (k / "Ważne" / "b.jpg").write_bytes(b"y")
    db = skaner.otworz_baze(tmp_path / "k.db")
    sprzatanie.usun_odlozone(db, [str(k)])
    assert (k / "Ważne" / "b.jpg").exists() and not (k / "Odłożone").exists()
    assert sprzatanie.odlozone([str(k)]) == {"kategorie": [], "plikow": 0, "bajty": 0}


def test_przelaczanie_trybow(tmp_path):
    stan = aplikacja.Stan(tmp_path / "dane")
    assert stan.projekt["typ"] == "porzadkowanie"
    porz = stan.pid
    assert stan.przelacz_tryb("sprzatanie") is None
    assert stan.projekt["typ"] == "sprzatanie" and stan.pid != porz and stan.stan()["projekt"]["typ"] == "sprzatanie"
    sprz = stan.pid
    assert stan.przelacz_tryb("porzadkowanie") is None and stan.pid == porz  # wraca do ostatniego projektu
    assert stan.przelacz_tryb("sprzatanie") is None and stan.pid == sprz  # i do tego samego sprzątania
    assert stan.przelacz_tryb("xyz")
