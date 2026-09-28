import os
import struct
from datetime import datetime, timezone

import pytest
from PIL import Image

from katalogator import metadane, raport, skaner, typy


def _jpg_z_exif(sciezka, data="2023:03:14 12:00:00", gps=(50.2811, 19.5625), model="SM-G991B"):
    im = Image.new("RGB", (8, 8), "white")
    exif = im.getexif()
    exif[0x010F] = "samsung"
    exif[0x0110] = model
    exif.get_ifd(0x8769)[36867] = data
    if gps:
        def dms(x):
            x = abs(x)
            st = int(x); mi = int((x - st) * 60); se = round(((x - st) * 60 - mi) * 60, 4)
            return (st, mi, se)
        g = exif.get_ifd(0x8825)
        g[1], g[2] = ("N" if gps[0] >= 0 else "S"), dms(gps[0])
        g[3], g[4] = ("E" if gps[1] >= 0 else "W"), dms(gps[1])
    im.save(sciezka, exif=exif)


def _box(typ, dane):
    return struct.pack(">I4s", 8 + len(dane), typ) + dane


def _mp4(sciezka, kiedy: datetime, xyz=b"+50.2811+019.5625/"):
    sek = int((kiedy - datetime(1904, 1, 1, tzinfo=timezone.utc)).total_seconds())
    mvhd = _box(b"mvhd", bytes([0, 0, 0, 0]) + struct.pack(">II", sek, sek) + b"\0" * 88)
    udta = _box(b"udta", _box(b"\xa9xyz", struct.pack(">HH", len(xyz), 0x15c7) + xyz))
    with open(sciezka, "wb") as f:
        f.write(_box(b"ftyp", b"isom\0\0\0\0isom"))
        f.write(_box(b"mdat", b"\0" * 64))
        f.write(_box(b"moov", mvhd + udta))  # moov na końcu, jak w wielu telefonach


def test_rodzaj_i_smieci():
    assert typy.rodzaj("A.JPG") == "zdjecie"
    assert typy.rodzaj("x.mov") == "film"
    assert typy.rodzaj("s.flac") == "muzyka"
    assert typy.rodzaj("f.srt") == "towarzyszacy"
    assert typy.rodzaj("umowa.pdf") == "inne"
    assert typy.pominac_folder(".wdmc") and typy.pominac_folder("@eaDir")
    assert typy.pominac_plik("Thumbs.db") and not typy.pominac_plik("zdjecie.jpg")


@pytest.mark.parametrize("nazwa,oczek", [
    ("IMG_20230714_153012.jpg", datetime(2023, 7, 14, 15, 30, 12)),
    ("PXL_20230714_153012345.jpg", datetime(2023, 7, 14, 15, 30, 12)),
    ("IMG-20230714-WA0001.jpg", datetime(2023, 7, 14)),
    ("VID-20211231-WA0003.mp4", datetime(2021, 12, 31)),
    ("Screenshot_2023-07-14-15-30-12.png", datetime(2023, 7, 14, 15, 30, 12)),
    ("20190101_000000.jpg", datetime(2019, 1, 1)),
    ("DSC01234.JPG", None),
    ("20231399_123456.jpg", None),
])
def test_data_z_nazwy(nazwa, oczek):
    assert metadane.data_z_nazwy(nazwa) == oczek


def test_exif_data_gps_aparat(tmp_path):
    p = tmp_path / "a.jpg"
    _jpg_z_exif(p)
    m = metadane.odczytaj(str(p), "zdjecie", 0)
    assert m.data == datetime(2023, 3, 14, 12) and m.zrodlo_daty == "exif"
    assert m.lat == pytest.approx(50.2811, abs=1e-4) and m.lon == pytest.approx(19.5625, abs=1e-4)
    assert m.aparat == "samsung SM-G991B"


def test_gps_poludnie_zachod(tmp_path):
    p = tmp_path / "b.jpg"
    _jpg_z_exif(p, gps=(-33.9, -70.6))
    m = metadane.odczytaj(str(p), "zdjecie", 0)
    assert m.lat < 0 and m.lon < 0


def test_zdjecie_bez_exif_bierze_date_z_nazwy_potem_z_pliku(tmp_path):
    p = tmp_path / "IMG-20200505-WA0007.jpg"
    Image.new("RGB", (4, 4)).save(p)
    m = metadane.odczytaj(str(p), "zdjecie", 0)
    assert (m.data, m.zrodlo_daty) == (datetime(2020, 5, 5), "nazwa")
    q = tmp_path / "kot.png"
    Image.new("RGB", (4, 4)).save(q)
    m = metadane.odczytaj(str(q), "zdjecie", 1_600_000_000)
    assert m.zrodlo_daty == "plik" and m.lat is None


def test_mp4_data_i_gps(tmp_path):
    p = tmp_path / "film.mp4"
    _mp4(p, datetime(2022, 7, 10, 10, 0, tzinfo=timezone.utc))
    m = metadane.odczytaj(str(p), "film", 0)
    assert m.zrodlo_daty == "film"
    assert m.data == datetime(2022, 7, 10, 10, 0, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    assert (m.lat, m.lon) == (50.2811, 19.5625)


def test_uszkodzony_plik_nie_przerywa(tmp_path):
    p = tmp_path / "zepsute.jpg"
    p.write_bytes(b"to nie jest jpg")
    m = metadane.odczytaj(str(p), "zdjecie", 1_600_000_000)
    assert m.blad and m.zrodlo_daty == "plik"


def test_muzyka_tagi(tmp_path):
    from mutagen.id3 import ID3, TALB, TIT2, TPE1
    p = tmp_path / "utwor.mp3"
    ramka = b"\xff\xfb\x90\x64" + b"\0" * 413  # MPEG1 L3 128 kb/s 44,1 kHz
    p.write_bytes(ramka * 20)
    t = ID3()
    t.add(TPE1(encoding=3, text="Dżem")); t.add(TALB(encoding=3, text="Detox")); t.add(TIT2(encoding=3, text="Wehikuł czasu"))
    t.save(p)
    m = metadane.odczytaj(str(p), "muzyka", 0)
    assert m.blad is None
    assert (m.wykonawca, m.album, m.tytul) == ("Dżem", "Detox", "Wehikuł czasu")


def _drzewo(tmp_path):
    k = tmp_path / "dysk"
    (k / "Zdjecia" / ".wdmc").mkdir(parents=True)
    (k / "Praca" / "2021").mkdir(parents=True)
    _jpg_z_exif(k / "Zdjecia" / "a.jpg")
    _jpg_z_exif(k / "Zdjecia" / "kopia_a.jpg")
    _jpg_z_exif(k / "Zdjecia" / "bez_gps.jpg", gps=None, data="2021:12:24 18:00:00")
    (k / "Zdjecia" / ".wdmc" / "a.jpg").write_bytes(b"miniatura")
    (k / "Zdjecia" / "Thumbs.db").write_bytes(b"x")
    _mp4(k / "Zdjecia" / "film.mp4", datetime(2022, 7, 10, tzinfo=timezone.utc))
    (k / "Praca" / "2021" / "faktura.pdf").write_bytes(b"%PDF" + b"0" * 100)
    (k / "Praca" / "notatki.txt").write_text("abc")
    return k


def test_skan_raport_i_wznawianie(tmp_path):
    k = _drzewo(tmp_path)
    db = skaner.otworz_baze(tmp_path / "k.db")
    w = skaner.skanuj(str(k), db, watki=2, wypisz=lambda *_: None)
    assert w["wszystkie"] == 6 and w["nowe_lub_zmienione"] == 6
    assert w["pominiete_pliki"] == 1 and w["pominiete_foldery"] == 1

    d = raport.zbierz(db)
    rodz = {r["rodzaj"]: r["n"] for r in d["rodzaje"]}
    assert rodz == {"zdjecie": 3, "film": 1, "inne": 2}
    assert d["media"]["zdjecie"]["gps"] == 2 and d["media"]["film"]["gps"] == 1
    assert {f["f"] for f in d["inne_foldery"]} == {"Praca"}
    assert d["duplikaty"]["nadmiar"] >= 1  # a.jpg i kopia_a.jpg
    txt = raport.tekst(d)
    assert "ZDJĘCIA: 3" in txt and "Praca" in txt
    assert "<html" in raport.html_raport(d)

    # Drugi skan: nic się nie zmieniło -> nic nie jest czytane ponownie.
    w2 = skaner.skanuj(str(k), db, watki=2, wypisz=lambda *_: None)
    assert w2["bez_zmian"] == 6 and w2["nowe_lub_zmienione"] == 0

    # Usunięty plik znika z bazy, nowy jest dodany.
    os.remove(k / "Praca" / "notatki.txt")
    (k / "Praca" / "nowy.docx").write_bytes(b"PK")
    w3 = skaner.skanuj(str(k), db, watki=2, wypisz=lambda *_: None)
    assert w3["usuniete_z_bazy"] == 1 and w3["nowe_lub_zmienione"] == 1
    assert db.execute("SELECT COUNT(*) FROM pliki").fetchone()[0] == 6


def test_cli(tmp_path, capsys):
    from katalogator.__main__ import main
    k = _drzewo(tmp_path)
    baza, html = tmp_path / "k.db", tmp_path / "r.html"
    assert main(["--baza", str(baza), "skanuj", str(k), "--bez-raportu"]) == 0
    assert main(["--baza", str(baza), "raport", "--html", str(html), "--nie-otwieraj"]) == 0
    assert html.exists() and "RAPORT" in capsys.readouterr().out
