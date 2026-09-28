import os
import shutil
from datetime import datetime, timezone

import pytest

from katalogator import analiza, planista, skaner, wykonawca
from test_katalogator import _jpg_z_exif, _mp4

OLKUSZ, HEL, RZYM = (50.2811, 19.5625), (54.6080, 18.8010), (41.9028, 12.4964)


@pytest.fixture
def swiat(tmp_path):
    k = tmp_path / "dysk"
    for f in ("Telefon", "Praca", "Filmy", "Muzyka"):
        (k / f).mkdir(parents=True)
    for i in range(4):
        _jpg_z_exif(k / "Telefon" / f"IMG_2023031{i}.jpg", data=f"2023:03:1{i} 12:00:00", gps=OLKUSZ)
    _jpg_z_exif(k / "Telefon" / "IMG_hel1.jpg", data="2023:07:10 10:00:00", gps=HEL)
    _jpg_z_exif(k / "Telefon" / "IMG_hel2.jpg", data="2023:07:11 18:00:00", gps=(54.70, 18.68))  # Jastarnia
    _jpg_z_exif(k / "Telefon" / "IMG_hel3.jpg", data="2023:07:12 09:00:00", gps=HEL)
    _jpg_z_exif(k / "Telefon" / "IMG_hel_bez_gps.jpg", data="2023:07:11 12:00:00", gps=None)
    _jpg_z_exif(k / "Telefon" / "IMG_rzym.jpg", data="2023:08:20 12:00:00", gps=RZYM)
    _jpg_z_exif(k / "Telefon" / "paragon.jpg", data="2023:03:15 12:00:00", gps=OLKUSZ)
    _jpg_z_exif(k / "Telefon" / "DSC_0001.jpg", data="2023:03:16 12:00:00", gps=OLKUSZ)
    (k / "Telefon" / "DSC_0001.xmp").write_text("<x/>")
    (k / "Telefon" / "DSC_0001.dng").write_bytes(b"RAW" * 100)
    _mp4(k / "Telefon" / "VID_20230711_120000.mp4", datetime(2023, 7, 11, 12, tzinfo=timezone.utc),
         xyz=b"+54.6080+018.8010/")
    (k / "Filmy" / "Film.2019.1080p.mkv").write_bytes(b"MKV" * 1000)
    (k / "Praca" / "umowa.pdf").write_bytes(b"%PDF" * 50)
    ramka = b"\xff\xfb\x90\x64" + b"\0" * 413
    from mutagen.id3 import ID3, TALB, TPE1
    (k / "Muzyka" / "01.mp3").write_bytes(ramka * 10)
    t = ID3(); t.add(TPE1(encoding=3, text="Dżem")); t.add(TALB(encoding=3, text="Detox")); t.save(k / "Muzyka" / "01.mp3")
    (k / "Muzyka" / "bez_tagow.mp3").write_bytes(ramka * 11)
    cel = tmp_path / "cel"
    (cel / "Zdjęcia" / "Stare").mkdir(parents=True)
    shutil.copy2(k / "Telefon" / "IMG_rzym.jpg", cel / "Zdjęcia" / "Stare" / "rzym_kopia.jpg")  # już jest w celu
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    skaner.skanuj(str(cel), db, wypisz=lambda *_: None)
    planista.przygotuj(db)
    pid = db.execute("SELECT rowid FROM pliki WHERE wzgledna LIKE '%paragon.jpg'").fetchone()[0]
    analiza.zapisz_decyzje(db, [pid], [])
    return k, cel, db


def _cele(db):
    return {os.path.basename(r["sciezka"]): (r["cel"], r["stan"], r["tryb"], r["uwaga"]) for r in db.execute("SELECT * FROM plan")}


def test_propozycja(swiat):
    k, cel, db = swiat
    w = planista.generuj(db, [{"sciezka": str(k), "tryb": "kopiuj"}], str(cel))
    c = _cele(db)
    z23 = "Zdjęcia/Zdjęcia z 2023/"
    assert c["IMG_20230310.jpg"][0] == z23 + "Marzec w domu/IMG_20230310.jpg"
    assert c["IMG_hel1.jpg"][0] == z23 + "Lipiec na Helu/IMG_hel1.jpg"
    assert c["IMG_hel2.jpg"][0] == z23 + "Lipiec na Helu/IMG_hel2.jpg"     # Jastarnia w ramach wyjazdu
    assert c["IMG_hel_bez_gps.jpg"][0].startswith(z23 + "Lipiec na Helu/")
    assert "bez GPS" in c["IMG_hel_bez_gps.jpg"][3]
    assert c["VID_20230711_120000.mp4"][0] == "Filmy/Filmy z 2023/Lipiec na Helu/VID_20230711_120000.mp4"
    assert c["IMG_rzym.jpg"][1] == "juz_jest"                              # identyczny plik jest już w celu
    assert c["paragon.jpg"][0] == "Zdjęcia/Dokumenty/paragon.jpg"
    assert c["DSC_0001.xmp"][0] == z23 + "Marzec w domu/DSC_0001.xmp"       # idzie za zdjęciem
    assert c["DSC_0001.dng"][0] == z23 + "Marzec w domu/DSC_0001.dng"
    assert c["01.mp3"][0] == "Muzyka/Dżem/Detox/01.mp3"
    assert c["bez_tagow.mp3"][0] == "Muzyka/Nieznany wykonawca/Nieznany album/bez_tagow.mp3"
    assert c["Film.2019.1080p.mkv"][0] == "Filmy/Inne/dysk/Filmy/Film.2019.1080p.mkv"
    assert c["umowa.pdf"][0] == "dysk/Praca/umowa.pdf"
    assert c["rzym_kopia.jpg"][2] == "istniejacy"
    assert w["dom"] == "Olkusz" and w["kopiuj"] == 17 and w["istniejace"] == 1
    foldery = {f["sciezka"]: f for f in planista.drzewo(db)}
    assert foldery["Zdjęcia/Stare"]["istniejace"] == 1
    assert foldery[z23 + "Lipiec na Helu"]["uwagi"] == 1


def test_zagranica(swiat, tmp_path):
    k, cel, db = swiat
    shutil.rmtree(cel / "Zdjęcia")
    skaner.skanuj(str(cel), db, wypisz=lambda *_: None)
    planista.generuj(db, [{"sciezka": str(k), "tryb": "kopiuj"}], str(cel))
    assert _cele(db)["IMG_rzym.jpg"][0] == "Zdjęcia/Zdjęcia z 2023/Sierpień we Włoszech/IMG_rzym.jpg"


def test_edycja_i_cofanie(swiat):
    k, cel, db = swiat
    planista.generuj(db, [{"sciezka": str(k), "tryb": "kopiuj"}], str(cel))
    hel = "Zdjęcia/Zdjęcia z 2023/Lipiec na Helu"
    w = planista.zmien_nazwe_folderu(db, hel, "Zdjęcia/Zdjęcia z 2023/Wakacje na Helu")
    assert w["zmienione"] == 4 and not w["scalono"]
    assert _cele(db)["IMG_hel1.jpg"][0] == "Zdjęcia/Zdjęcia z 2023/Wakacje na Helu/IMG_hel1.jpg"
    # scalenie: przenosimy do istniejącego folderu -> kolizja nazwy dostaje (2)
    ids = [r["id"] for r in db.execute("SELECT id FROM plan WHERE sciezka LIKE '%IMG_20230310.jpg'")]
    planista.przenies_pliki(db, ids, "Zdjęcia/Zdjęcia z 2023/Wakacje na Helu")
    dom = "Zdjęcia/Zdjęcia z 2023/Marzec w domu"
    w = planista.zmien_nazwe_folderu(db, dom, "Zdjęcia/Zdjęcia z 2023/Wakacje na Helu")
    assert w["scalono"]
    assert planista.pliki_folderu(db, "Zdjęcia/Zdjęcia z 2023/Wakacje na Helu")["razem"] == 4 + 1 + 6
    planista.wyklucz(db, folder="Muzyka")
    assert planista.podsumowanie(db)["pominiete"] >= 2
    # cofnij wszystko po kolei
    for _ in range(4):
        planista.cofnij(db)
    assert _cele(db)["IMG_hel1.jpg"][0] == hel + "/IMG_hel1.jpg"
    assert _cele(db)["IMG_20230310.jpg"][0] == dom + "/IMG_20230310.jpg"
    planista.ponow(db)
    assert _cele(db)["IMG_hel1.jpg"][0] == "Zdjęcia/Zdjęcia z 2023/Wakacje na Helu/IMG_hel1.jpg"
    # nowa operacja kasuje możliwość „ponów”
    planista.wyklucz(db, folder="Muzyka")
    assert planista.ponow(db)["zmienione"] == 0
    assert "blad" in planista.zmien_nazwe_folderu(db, "Muzyka", "Muzyka/Muzyka")


def test_wykonanie_kopiuj_i_cofnij(swiat):
    k, cel, db = swiat
    planista.generuj(db, [{"sciezka": str(k), "tryb": "kopiuj"}], str(cel))
    w = wykonawca.wykonaj(db)
    assert w["zrobione"] == 17 and w["bledy"] == 0
    doc = cel / "Zdjęcia" / "Dokumenty" / "paragon.jpg"
    assert doc.read_bytes() == (k / "Telefon" / "paragon.jpg").read_bytes()
    assert os.path.getmtime(doc) == pytest.approx(os.path.getmtime(k / "Telefon" / "paragon.jpg"), abs=1)
    assert (k / "Telefon" / "paragon.jpg").exists()          # kopiowanie zostawia oryginał
    assert not list(cel.rglob("*" + wykonawca.TMP))
    assert wykonawca.wykonaj(db)["zrobione"] == 0            # drugi raz nic nie robi
    c = wykonawca.cofnij(db)
    assert c["cofniete"] == 17 and not c["bledy"] and not doc.exists()
    assert not (cel / "Zdjęcia" / "Dokumenty").exists() and (cel / "Zdjęcia" / "Stare").exists()


def test_wykonanie_przenies_usuwa_puste_i_cofa(swiat):
    k, cel, db = swiat
    planista.generuj(db, [{"sciezka": str(k / "Praca"), "tryb": "przenies"},
                          {"sciezka": str(k / "Muzyka"), "tryb": "kopiuj"}], str(cel))
    (k / "Praca" / "Thumbs.db").write_bytes(b"x")
    w = wykonawca.wykonaj(db)
    assert w["zrobione"] == 3 and (cel / "Praca" / "umowa.pdf").exists()
    assert not (k / "Praca").exists() and w["usuniete_foldery"] == 1  # pusty (poza Thumbs.db) folder usunięty
    assert (k / "Muzyka" / "01.mp3").exists()
    wykonawca.cofnij(db)
    assert (k / "Praca" / "umowa.pdf").exists() and not (cel / "Praca" / "umowa.pdf").exists()


def test_weryfikacja_chroni_oryginal(swiat, monkeypatch):
    k, cel, db = swiat
    planista.generuj(db, [{"sciezka": str(k / "Praca"), "tryb": "przenies"}], str(cel))
    monkeypatch.setattr(wykonawca, "ten_sam_wolumin", lambda a, b: False)  # wymuś kopiowanie
    monkeypatch.setattr(wykonawca, "_hash", lambda *a, **kw: "zly")
    w = wykonawca.wykonaj(db)
    assert w["bledy"] == 1 and (k / "Praca" / "umowa.pdf").exists()
    assert not (cel / "Praca" / "umowa.pdf").exists() and not list(cel.rglob("*" + wykonawca.TMP))
    assert db.execute("SELECT wynik FROM plan WHERE sciezka LIKE '%umowa.pdf'").fetchone()[0].startswith("blad")


def test_za_malo_miejsca(swiat, monkeypatch):
    k, cel, db = swiat
    planista.generuj(db, [{"sciezka": str(k), "tryb": "kopiuj"}], str(cel))
    monkeypatch.setattr(wykonawca.shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(10, 9, 1))
    with pytest.raises(OSError, match="Za mało miejsca"):
        wykonawca.wykonaj(db)


def test_nie_nadpisuje(swiat):
    k, cel, db = swiat
    planista.generuj(db, [{"sciezka": str(k / "Praca"), "tryb": "kopiuj"}], str(cel))
    (cel / "Praca").mkdir()
    (cel / "Praca" / "umowa.pdf").write_bytes(b"inna tresc")  # pojawił się po skanie
    wykonawca.wykonaj(db)
    assert (cel / "Praca" / "umowa.pdf").read_bytes() == b"inna tresc"
    assert (cel / "Praca" / "umowa (2).pdf").exists()
