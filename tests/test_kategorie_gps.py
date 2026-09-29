"""1.4: śmieci i obrazy „nie z aparatu”, dokumenty po latach, Odłożone, GPS z XMP / Google Takeout / nazwy folderu."""
import json
import os

from PIL import Image

from katalogator import kategorie, metadane, miejsca, planista, skaner
from test_katalogator import _jpg_z_exif


def test_stopnie_rozne_zapisy():
    assert round(metadane._stopnie((50, 16, 52.0), "N"), 4) == 50.2811
    assert round(metadane._stopnie((50, 16.8667), b"N"), 4) == 50.2811  # (st, min)
    assert metadane._stopnie((19.5625,), "W") == -19.5625               # same stopnie
    assert metadane._stopnie((float("nan"), 0, 0), "N") is None          # 0/0 z aparatu


def test_gps_z_xmp_w_pliku(tmp_path):
    xmp = (b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
           b'<rdf:Description xmlns:exif="http://ns.adobe.com/exif/1.0/" exif:GPSLatitude="54,36.48N" '
           b'exif:GPSLongitude="18,48.06E" exif:DateTimeOriginal="2019-07-10T10:00:00"/></rdf:RDF></x:xmpmeta>')
    p = tmp_path / "z_lightrooma.jpg"
    Image.new("RGB", (64, 48), "white").save(p, xmp=xmp)
    m = metadane.odczytaj(str(p), "zdjecie", 0)
    assert m.lat is not None and abs(m.lat - 54.608) < 0.001 and abs(m.lon - 18.801) < 0.001
    assert m.zrodlo_daty == "exif" and m.data.year == 2019


def test_takeout_json_obok_zdjecia_i_razem_w_drzewie(tmp_path):
    k = tmp_path / "Takeout" / "Zdjęcia z 2018"
    k.mkdir(parents=True)
    Image.new("RGB", (1600, 1200), (90, 120, 160)).save(k / "IMG_0001.jpg", quality=80)  # bez EXIF
    (k / "IMG_0001.jpg.supplemental-metadata.json").write_text(json.dumps({
        "photoTakenTime": {"timestamp": "1531216800"},
        "geoData": {"latitude": 0.0, "longitude": 0.0},
        "geoDataExif": {"latitude": 54.608, "longitude": 18.801}}), encoding="utf-8")
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(tmp_path / "Takeout"), db, wypisz=lambda *_: None)
    r = db.execute("SELECT lat, lon, zrodlo_daty, data FROM pliki WHERE wzgledna LIKE '%IMG_0001.jpg'").fetchone()
    assert abs(r["lat"] - 54.608) < 1e-3 and r["zrodlo_daty"] == "exif" and r["data"].startswith("2018-07-10")
    planista.generuj(db, [{"sciezka": str(tmp_path / "Takeout"), "tryb": "kopiuj"}], str(tmp_path / "cel"), dom="Olkusz")
    cele = {os.path.basename(r[0]): r[1] for r in db.execute("SELECT sciezka, cel FROM plan")}
    folder_zdj = cele["IMG_0001.jpg"].rsplit("/", 1)[0]
    assert folder_zdj.endswith("Lipiec na Helu")
    assert cele["IMG_0001.jpg.supplemental-metadata.json"].rsplit("/", 1)[0] == folder_zdj  # json idzie za zdjęciem


def test_miejsce_z_nazwy_folderu():
    assert miejsca.z_folderu("2004 Zakopane/IMG_1.jpg") == "Zakopane"
    assert miejsca.z_folderu("Wakacje Hel 2005/a.jpg") == "Hel"
    assert miejsca.z_folderu("Zdjęcia/Chorwacja 2019/x.jpg") == "@HR"
    assert miejsca.z_folderu("krakow 2003/x.jpg") == "Kraków"
    assert miejsca.z_folderu("Rodzinne/Wigilia/x.jpg") is None
    assert miejsca.z_folderu("Zakopane.jpg") is None  # tylko foldery, nie nazwa pliku


def test_smieci_i_podejrzane():
    p = {"sciezka": "C:/Users/X/AppData/Local/Temp/Zdjecia/a.jpg", "wzgledna": "a.jpg", "rozmiar": 5000,
         "rodzaj": "zdjecie", "aparat": None, "lat": None, "zrodlo_daty": "plik"}
    assert kategorie.smieci(p) is None  # „Temp” nad wybranym folderem nie ma znaczenia
    assert kategorie.smieci({**p, "rozmiar": 0})
    assert kategorie.smieci({**p, "sciezka": "x/ikona.ico", "wzgledna": "ikona.ico"})
    assert kategorie.smieci({**p, "wzgledna": ".thumbnails/a.jpg"})
    assert kategorie.smieci(p, (48, 48))
    assert kategorie.smieci({**p, "aparat": "Canon EOS"}, (48, 48)) is None  # zdjęcie z aparatu nie jest ikoną
    assert "zrzut" in kategorie.podejrzane({**p, "sciezka": "x/Screenshot_2023.png", "wzgledna": "Screenshot_2023.png"})
    assert kategorie.podejrzane({**p, "wzgledna": "Pobrane/mem.jpg"})
    assert kategorie.podejrzane({**p, "aparat": "SM-G991B"}) is None
    assert kategorie.podejrzane({**p, "sciezka": "x/IMG-20230605-WA0001.jpg", "wzgledna": "IMG-20230605-WA0001.jpg",
                                 "zrodlo_daty": "nazwa"}, (1600, 1200)) is None  # zdjęcie z WhatsAppa


def test_decyzje_przekladaja_plan(tmp_path):
    k = tmp_path / "dysk"
    (k / "Pobrane").mkdir(parents=True)
    _jpg_z_exif(k / "IMG_20230310.jpg", data="2023:03:10 12:00:00")
    Image.new("RGB", (1200, 900), (30, 90, 200)).save(k / "Pobrane" / "grafika.png")
    Image.new("RGB", (1200, 900), (240, 240, 240)).save(k / "Pobrane" / "skan.png")
    (k / "Pobrane" / "stary.tmp").write_bytes(b"x" * 10)
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    planista.generuj(db, [{"sciezka": str(k), "tryb": "kopiuj"}], str(tmp_path / "cel"))
    cel = lambda n: db.execute("SELECT cel, kat FROM plan WHERE sciezka LIKE ?", ("%" + n,)).fetchone()
    assert cel("stary.tmp")["cel"].startswith("Odłożone/Śmieci/") and cel("stary.tmp")["kat"] == "smieci"
    assert cel("grafika.png")["kat"] == "podejrzane"
    ids = {r["wzgledna"].split("/")[-1]: r["id"] for r in db.execute("SELECT rowid id, wzgledna FROM pliki")}
    kategorie.zapisz(db, {ids["grafika.png"]: "smieci", ids["skan.png"]: "dokument"})
    planista.zastosuj_kategorie(db)
    assert cel("grafika.png")["cel"] == "Odłożone/Śmieci/Pobrane/grafika.png"
    assert cel("skan.png")["cel"].startswith("Dokumenty/Dokumenty z ") and cel("skan.png")["kat"] == "dokument"
    # zmiana zdania: to jednak zwykłe zdjęcie -> wraca tam, gdzie trafiłoby zdjęcie
    kategorie.zapisz(db, {ids["skan.png"]: "zdjecie"})
    planista.zastosuj_kategorie(db)
    assert cel("skan.png")["cel"].startswith("Zdjęcia/") and cel("skan.png")["kat"] is None
    planista.cofnij(db)
    assert cel("skan.png")["cel"].startswith("Dokumenty/")
