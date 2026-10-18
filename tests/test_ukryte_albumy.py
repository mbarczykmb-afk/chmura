"""🙈 Ukryte albumy (np. „Praca”): znikają z osi czasu i szukania, na telefonie nie ma ich wcale; przełącznik."""
from PIL import Image

from katalogator import galeria, skaner


def _exif(d):
    e = Image.Exif()
    e[0x8769] = {0x9003: d}
    return e


def test_ukryty_album_i_przelacznik(tmp_path):
    k = tmp_path / "z"
    k.mkdir()
    for i in range(4):
        Image.new("RGB", (50, 50)).save(k / f"{i}.jpg", exif=_exif(f"2021:05:0{i + 1} 12:00:00"))
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    db.close()
    g = galeria.Galeria(tmp_path / "k.db")
    ids = [p["id"] for p in g.pliki("2021", None)["pliki"]]
    al = g.album_nowy("Praca", ids[:2])["id"]
    g.album_ukryj(al)
    assert g.pliki("2021", None)["razem"] == 2 and g.szukaj("2021")["razem"] == 2
    galeria._FILTR.okno = True  # okno programu: album widać i można go otworzyć
    assert [a["ukryty"] for a in g.albumy()["albumy"]] == [True] and g.kolekcja("album", al)["razem"] == 2
    galeria._FILTR.okno = False  # telefon: ani albumu, ani jego zdjęć
    assert g.albumy()["albumy"] == [] and "blad" in g.kolekcja("album", al)
    assert g.plik(ids[0]) is None
    g.ustaw_ukrywanie(False)  # przełącznik: pokaż wszystko — także w innej galerii tej samej bazy
    assert galeria.Galeria(tmp_path / "k.db").pliki("2021", None)["razem"] == 4
    g.ustaw_ukrywanie(True)
    g.album_ukryj(al, False)
    assert g.pliki("2021", None)["razem"] == 4


def test_foldery_i_albumy_przy_zdjeciach(tmp_path):
    k = tmp_path / "z"
    for sub in ("2020/05 Hel", "2020/06 Tatry", "2021"):
        (k / sub).mkdir(parents=True)
        for i in range(2):
            Image.new("RGB", (50, 50)).save(k / sub / f"{i}.jpg", exif=_exif("2021:05:01 12:00:00"))
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    db.close()
    g = galeria.Galeria(tmp_path / "k.db")
    assert sorted(n for _, n in g.foldery()["foldery"]) == [2, 2, 2]
    assert g.folder(str(k / "2020"))["razem"] == 0 and g.folder(str(k / "2020"), True)["razem"] == 4
    assert g.folder(str(k / "2020" / "06 Tatry"))["nazwa"] == "06 Tatry"
    ids = [p["id"] for p in g.pliki("2021", None)["pliki"]]
    g.album_nowy("Praca", ids[:1])
    assert [p["albumy"] for p in g.pliki("2021", None)["pliki"]].count("Praca") == 1
