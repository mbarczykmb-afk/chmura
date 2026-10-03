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
    assert c["paragon.jpg"][0] == "Dokumenty/Dokumenty z 2023 (Telefon)/paragon.jpg"
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
    doc = cel / "Dokumenty" / "Dokumenty z 2023 (Telefon)" / "paragon.jpg"
    assert doc.read_bytes() == (k / "Telefon" / "paragon.jpg").read_bytes()
    assert os.path.getmtime(doc) == pytest.approx(os.path.getmtime(k / "Telefon" / "paragon.jpg"), abs=1)
    assert (k / "Telefon" / "paragon.jpg").exists()          # kopiowanie zostawia oryginał
    assert not list(cel.rglob("*" + wykonawca.TMP))
    assert wykonawca.wykonaj(db)["zrobione"] == 0            # drugi raz nic nie robi
    c = wykonawca.cofnij(db)
    assert c["cofniete"] == 17 and not c["bledy"] and not doc.exists()
    assert not (cel / "Dokumenty").exists() and (cel / "Zdjęcia" / "Stare").exists()


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
    monkeypatch.setattr(wykonawca, "_sumy_kawalkow", lambda *a, **kw: ["zly"])  # kopia „różni się”
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


def test_szukaj_i_filtry(swiat):
    k, cel, db = swiat
    planista.generuj(db, [{"sciezka": str(k), "tryb": "kopiuj"}], str(cel))
    assert {p["nazwa"] for p in planista.szukaj(db, "hel")["pliki"]} >= {"IMG_hel1.jpg", "IMG_hel_bez_gps.jpg"}
    assert planista.szukaj(db, "HELU")["razem"] >= 4  # szukanie także po nazwie folderu, bez wielkości liter
    assert [p["nazwa"] for p in planista.szukaj(db, "", "bez_gps")["pliki"]] == ["IMG_hel_bez_gps.jpg"]
    assert {p["nazwa"] for p in planista.szukaj(db, "", "pominiete")["pliki"]} == {"IMG_rzym.jpg"}
    assert planista.szukaj(db, "", "uwagi")["razem"] >= 2


def test_ustaw_miejsce_i_date(swiat):
    k, cel, db = swiat
    planista.generuj(db, [{"sciezka": str(k), "tryb": "kopiuj"}], str(cel))
    ids = [r["id"] for r in db.execute("SELECT id FROM plan WHERE sciezka LIKE '%IMG_2023031%'")]
    w = planista.ustaw_miejsce(db, ids, "Zakopane")
    assert w["zmienione"] == 4 and w["foldery"] == ["Zdjęcia/Zdjęcia z 2023/Marzec w Zakopanem"]
    assert planista.ustaw_miejsce(db, ids, "dom")["foldery"] == ["Zdjęcia/Zdjęcia z 2023/Marzec w domu"]
    pdf = db.execute("SELECT id FROM plan WHERE sciezka LIKE '%umowa.pdf'").fetchone()[0]
    assert planista.ustaw_miejsce(db, [pdf], "Hel")["pominiete"] == 1  # nie-media pomijane
    # data: zmiana roku/miesiąca zachowuje miejsce
    hel = [r["id"] for r in db.execute("SELECT id FROM plan WHERE sciezka LIKE '%IMG_hel1.jpg'")]
    w = planista.ustaw_date(db, hel, "2019-08-03")
    assert w["foldery"] == ["Zdjęcia/Zdjęcia z 2019/Sierpień na Helu"]
    assert db.execute("SELECT data FROM plan WHERE id=?", hel).fetchone()[0].startswith("2019-08-03")
    planista.cofnij(db)
    r = db.execute("SELECT cel, data FROM plan WHERE id=?", hel).fetchone()
    assert r[0] == "Zdjęcia/Zdjęcia z 2023/Lipiec na Helu/IMG_hel1.jpg" and r[1].startswith("2023-07-10")
    planista.ponow(db)
    assert db.execute("SELECT data FROM plan WHERE id=?", hel).fetchone()[0].startswith("2019-08-03")
    assert "blad" in planista.ustaw_date(db, hel, "03.08.2019")
    assert "blad" in planista.ustaw_miejsce(db, hel, " ")


def test_najpierw_kopiuj_potem_przenies(swiat):
    """Skopiowane wcześniej, teraz „przenieś”: oryginały znikają (po sprawdzeniu kopii), bez kopii „ (2)”."""
    k, cel, db = swiat
    planista.generuj(db, [{"sciezka": str(k), "tryb": "kopiuj"}], str(cel))
    assert wykonawca.wykonaj(db)["zrobione"] == 17
    przed = sorted(p.relative_to(cel) for p in cel.rglob("*") if p.is_file())
    # nowa propozycja rozpoznaje skopiowane pliki w bibliotece po zawartości
    planista.generuj(db, [{"sciezka": str(k), "tryb": "przenies"}], str(cel))
    p = planista.podsumowanie(db)
    assert p["oryginaly"] == 18 and p["kopiuj"] == p["przenies"] == 0  # 17 + zdjęcie z Rzymu, które już było
    s = wykonawca.sprawdz(db)
    assert s["oryginaly"] == 18 and s["potrzeba"] == 0
    w = wykonawca.wykonaj(db)
    assert w["zrobione"] == 18 and w["bledy"] == 0
    assert not [x for x in k.rglob("*") if x.is_file()]           # oryginały usunięte
    assert sorted(p.relative_to(cel) for p in cel.rglob("*") if p.is_file()) == przed  # biblioteka bez zmian
    c = wykonawca.cofnij(db)                                        # cofnięcie przywraca oryginały z kopii
    assert c["cofniete"] == 18 and not c["bledy"]
    assert (k / "Telefon" / "paragon.jpg").exists() and (k / "Telefon" / "IMG_rzym.jpg").exists()
    assert sorted(p.relative_to(cel) for p in cel.rglob("*") if p.is_file()) == przed


def test_bez_usuwania_oryginalow(swiat):
    k, cel, db = swiat
    planista.generuj(db, [{"sciezka": str(k / "Praca"), "tryb": "kopiuj"}], str(cel))
    wykonawca.wykonaj(db)
    planista.generuj(db, [{"sciezka": str(k / "Praca"), "tryb": "przenies"}], str(cel))
    assert wykonawca.wykonaj(db, usun_oryginaly=False)["zrobione"] == 0
    assert (k / "Praca" / "umowa.pdf").exists()


def test_zmieniona_kopia_chroni_oryginal(swiat):
    k, cel, db = swiat
    planista.generuj(db, [{"sciezka": str(k / "Praca"), "tryb": "kopiuj"}], str(cel))
    wykonawca.wykonaj(db)
    planista.generuj(db, [{"sciezka": str(k / "Praca"), "tryb": "przenies"}], str(cel))
    kopia = next(cel.rglob("umowa.pdf"))
    kopia.write_bytes(b"%PDF" * 49 + b"XXXX")  # ten sam rozmiar, inna treść
    w = wykonawca.wykonaj(db)
    assert w["zrobione"] == 0 and w["bledy"] == 1
    assert (k / "Praca" / "umowa.pdf").read_bytes() == b"%PDF" * 50  # oryginał został
    assert "oryginał zostaje" in db.execute("SELECT wynik FROM plan WHERE stan='juz_jest'").fetchone()[0]


def test_zmiana_trybu_w_istniejacej_propozycji(swiat):
    k, cel, db = swiat
    planista.generuj(db, [{"sciezka": str(k / "Praca"), "tryb": "kopiuj"},
                          {"sciezka": str(k / "Telefon"), "tryb": "kopiuj"}], str(cel))
    z = planista.zmien_tryb(db, [{"sciezka": str(k / "Praca"), "tryb": "przenies"},
                                 {"sciezka": str(k / "Telefon"), "tryb": "kopiuj"}])
    assert z["zmienione"] == 1 and planista.podsumowanie(db)["przenies"] == 1
    w = wykonawca.wykonaj(db)
    assert w["bledy"] == 0 and not (k / "Praca" / "umowa.pdf").exists() and (k / "Telefon" / "paragon.jpg").exists()


def test_przelaczenie_na_przenies_po_kopiowaniu_bez_nowej_propozycji(swiat):
    """Samo przełączenie K → P w projekcie po kopiowaniu: „Uporządkuj” od razu usuwa oryginały (Drzewo zostaje)."""
    k, cel, db = swiat
    planista.generuj(db, [{"sciezka": str(k), "tryb": "kopiuj"}], str(cel))
    wykonawca.wykonaj(db)
    przed = sorted(p.relative_to(cel) for p in cel.rglob("*") if p.is_file())
    z = planista.zmien_tryb(db, [{"sciezka": str(k), "tryb": "przenies"}])
    assert z == {"zmienione": 1, "juz_skopiowane": 17}  # 1 = zdjęcie z Rzymu, które już było w celu
    p = planista.podsumowanie(db)
    assert p["oryginaly"] == 18 and p["kopiuj"] == p["przenies"] == 0
    w = wykonawca.wykonaj(db)
    assert w["zrobione"] == 18 and w["bledy"] == 0
    assert not [x for x in k.rglob("*") if x.is_file()]
    assert sorted(p.relative_to(cel) for p in cel.rglob("*") if p.is_file()) == przed
    wykonawca.cofnij(db)
    assert (k / "Telefon" / "paragon.jpg").exists()


def test_foldery_dokumentow_z_nazwami_zrodel(tmp_path):
    """„Dokumenty z 2023 (Faktury, Skany)” — w nawiasie foldery, z których pochodzą dokumenty; nazwy plików unikalne."""
    from katalogator import planista as pl
    db = skaner.otworz_baze(tmp_path / "k.db")
    pl.przygotuj(db)
    wiersze = [("/d/Skany/a.jpg", "Dokumenty/Dokumenty z 2023/a.jpg"), ("/d/Faktury/b.jpg", "Dokumenty/Dokumenty z 2023/b.jpg"),
               ("/d/Faktury/c.jpg", "Dokumenty/Dokumenty z 2023/c.jpg"),
               ("/d/Inne/a.jpg", "Dokumenty/Dokumenty z 2023 (Stare)/a.jpg"),  # dawny dopisek — złączony, a.jpg → a (2).jpg
               ("/d/X/z.jpg", "Moje/Dokumenty/z.jpg")]
    for sc, cel in wiersze:
        db.execute("INSERT INTO plan(plik_id, sciezka, rodzaj, rozmiar, cel, tryb, stan, kat) VALUES (1,?,?,?,?,?,?,?)",
                   (sc, "zdjecie", 1, cel, "kopiuj", "nowy", "dokument"))
    assert pl.opisz_foldery_dokumentow(db) == 4
    cele = sorted(r[0] for r in db.execute("SELECT cel FROM plan"))
    f = "Dokumenty/Dokumenty z 2023 (Faktury, Inne, Skany)"
    assert cele == sorted(["Moje/Dokumenty/z.jpg", f + "/a (2).jpg", f + "/a.jpg", f + "/b.jpg", f + "/c.jpg"])
    assert pl.opisz_foldery_dokumentow(db) == 0  # drugi raz — bez zmian


def test_aktualnosc_drzewa_po_odlozeniu(tmp_path):
    from katalogator import duplikaty, planista as pl
    k = tmp_path / "zdj"
    k.mkdir()
    _jpg_z_exif(k / "a.jpg", data="2021:05:01 12:00:00", gps=None)
    (k / "kopia.jpg").write_bytes((k / "a.jpg").read_bytes())
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    duplikaty.szukaj(db)
    pl.generuj(db, [{"sciezka": str(k), "tryb": "kopiuj"}], str(tmp_path / "cel"))
    a = pl.aktualnosc(db)
    assert a["jest"] and not a["nieaktualny"] and a["reczne"] == 0
    g = duplikaty.grupy(db, None, 0, 5)[0]
    duplikaty.przenies(db, [{"zostaw": g["zostaw"], "usun": [p["id"] for p in g["pliki"] if p["id"] != g["zostaw"]]}])
    a = pl.aktualnosc(db)
    assert a["nieaktualny"] and "odłożono" in a["powod"]
    pl.zmien_nazwe_folderu(db, "Zdjęcia", "Moje zdjęcia")  # ręczna poprawka — utworzenie od nowa by ją skasowało
    assert pl.aktualnosc(db)["reczne"] == 1
    pl.generuj(db, [{"sciezka": str(k), "tryb": "kopiuj"}], str(tmp_path / "cel"))
    assert not pl.aktualnosc(db)["nieaktualny"]


def test_uwagi_hurtem(swiat):
    k, cel, db = swiat
    planista.generuj(db, [{"sciezka": str(k), "tryb": "kopiuj"}], str(cel))
    rodzaje = planista.rodzaje_uwag(db)
    assert rodzaje and all(r["n"] > 0 for r in rodzaje)
    r0 = rodzaje[0]
    przed = planista.podsumowanie(db)["uwagi"]
    w = planista.przyjmij_uwagi(db, r0["rodzaj"])
    assert w["zmienione"] == r0["n"]
    assert r0["rodzaj"] not in {r["rodzaj"] for r in planista.rodzaje_uwag(db)}
    assert planista.podsumowanie(db)["uwagi"] < przed
    # drzewo od nowa — przyjęte uwagi nie wracają
    planista.generuj(db, [{"sciezka": str(k), "tryb": "kopiuj"}], str(cel))
    assert r0["rodzaj"] not in {r["rodzaj"] for r in planista.rodzaje_uwag(db)}
    # cofnięcie przyjęcia (po nowym drzewie nie ma czego przywracać, ale rodzaj znów jest pokazywany)
    planista.cofnij_uwagi(db, r0["rodzaj"])
    planista.generuj(db, [{"sciezka": str(k), "tryb": "kopiuj"}], str(cel))
    assert r0["rodzaj"] in {r["rodzaj"] for r in planista.rodzaje_uwag(db)}
