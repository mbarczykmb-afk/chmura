"""Wspólny indeks: plik przeczytany w jednym trybie/projekcie nie jest czytany z dysku drugi raz."""

import os

from katalogator import analiza, duplikaty, indeks, skaner
from test_katalogator import _jpg_z_exif

OLKUSZ = (50.2811, 19.5625)


def test_drugi_projekt_nie_czyta_plikow_drugi_raz(tmp_path, monkeypatch):
    k = tmp_path / "MyCloud"
    k.mkdir()
    for i in range(5):
        _jpg_z_exif(k / f"IMG_2023031{i}.jpg", data=f"2023:03:1{i} 12:00:00", gps=OLKUSZ)
    (k / "kopia.jpg").write_bytes((k / "IMG_20230310.jpg").read_bytes())
    indeks.ustaw(tmp_path / "wspolny.db")
    odczyty = {"meta": 0, "odcisk": 0, "analiza": 0}
    for nazwa, mod, fun, klucz in (("odczytaj", skaner, skaner.odczytaj, "meta"),
                                   ("_odcisk", duplikaty, duplikaty._odcisk, "odcisk"),
                                   ("_analizuj_plik", analiza, analiza._analizuj_plik, "analiza")):
        def licznik(*a, _f=fun, _k=klucz, **kw):
            odczyty[_k] += 1
            return _f(*a, **kw)
        monkeypatch.setattr(mod, nazwa, licznik)

    def wszystko(baza):
        db = skaner.otworz_baze(baza)
        skaner.skanuj(str(k), db, wypisz=lambda *_: None)
        duplikaty.szukaj(db)
        analiza.analizuj(db)
        return db
    a = wszystko(tmp_path / "porzadkowanie.db")
    pierwsze = dict(odczyty)
    assert pierwsze["meta"] == 6 and pierwsze["odcisk"] >= 2 and pierwsze["analiza"] == 6
    b = wszystko(tmp_path / "sprzatanie.db")  # inny projekt, te same pliki
    assert odczyty == pierwsze  # nic nie przeczytane z dysku ponownie
    # wyniki takie same jak przy odczycie z dysku
    for zap in ("SELECT sciezka, data, lat, lon, aparat FROM pliki ORDER BY sciezka",
                "SELECT sciezka, dhash, ostrosc FROM analiza ORDER BY sciezka"):
        assert [tuple(r) for r in a.execute(zap)] == [tuple(r) for r in b.execute(zap)]
    assert duplikaty.podsumowanie(b)["nadmiar"] == 1
    # zmieniony plik — czytany od nowa
    _jpg_z_exif(k / "IMG_20230311.jpg", data="2020:01:01 12:00:00", gps=None)
    os.utime(k / "IMG_20230311.jpg", (1_700_000_000, 1_700_000_000))
    c = skaner.otworz_baze(tmp_path / "przegladarka.db")
    skaner.skanuj(str(k), c, wypisz=lambda *_: None)
    assert odczyty["meta"] == pierwsze["meta"] + 1
    assert c.execute("SELECT data FROM pliki WHERE sciezka LIKE '%IMG_20230311.jpg'").fetchone()[0].startswith("2020")


def test_bez_indeksu_zwykly_odczyt(tmp_path):
    k = tmp_path / "d"
    k.mkdir()
    _jpg_z_exif(k / "IMG_1.jpg", data="2023:03:10 12:00:00", gps=None)
    indeks.ustaw(tmp_path / "brak" / "wspolny.db")  # nie da się utworzyć — indeks się wyłącza
    assert not indeks.wlaczony()
    db = skaner.otworz_baze(tmp_path / "k.db")
    assert skaner.skanuj(str(k), db, wypisz=lambda *_: None)["wszystkie"] == 1


def test_znikniete_pliki_usuwane_z_indeksu(tmp_path):
    k = tmp_path / "d"
    k.mkdir()
    _jpg_z_exif(k / "IMG_1.jpg", data="2023:03:10 12:00:00", gps=None)
    _jpg_z_exif(k / "IMG_2.jpg", data="2023:03:11 12:00:00", gps=None)
    indeks.ustaw(tmp_path / "wspolny.db")
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    (k / "IMG_2.jpg").unlink()
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    s1 = str(k / "IMG_1.jpg")
    assert set(indeks.pobierz("meta", [(s1, os.path.getsize(s1), os.path.getmtime(s1))])) == {s1}
    import sqlite3
    assert sqlite3.connect(tmp_path / "wspolny.db").execute("SELECT COUNT(*) FROM meta").fetchone()[0] == 1
