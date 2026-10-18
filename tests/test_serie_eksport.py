"""🔀 serie, 📦 eksport, ✎ zmiana nazw, 📷 filtry aparat / pora dnia, dane EXIF i histogram."""
import os

from PIL import Image

from katalogator import galeria, skaner


def _exif(d, aparat="Canon EOS", gps=False):
    e = Image.Exif()
    e[0x0110] = aparat
    e[0x8769] = {0x9003: d, 0x829D: (28, 10), 0x8827: 400}
    if gps:
        e[0x8825] = {1: "N", 2: (52.0, 13.0, 0.0), 3: "E", 4: (21.0, 0.0, 0.0)}
    return e


def _galeria(tmp_path):
    k = tmp_path / "z"
    k.mkdir()
    for i in range(4):  # seria: co 2 s
        Image.new("RGB", (1200, 800), (i * 50, 90, 90)).save(k / f"S_{i}.jpg", exif=_exif(f"2021:07:14 14:35:0{i * 2}", gps=True))
    Image.new("RGB", (800, 600)).save(k / "noc.jpg", exif=_exif("2021:07:14 23:30:00", "Samsung"))
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    db.close()
    galeria._FILTR.okno = True
    return k, galeria.Galeria(tmp_path / "k.db")


def test_serie_i_filtry(tmp_path):
    k, g = _galeria(tmp_path)
    s = g.serie()
    assert s["razem"] == 1 and s["serie"][0]["n"] == 4
    ids = s["serie"][0]["ids"]
    assert g.seria(ids[1])["ids"] == ids
    assert set(g.ostrosc(ids)["ostrosc"]) == {str(i) for i in ids}
    galeria._FILTR.aparat = "Samsung"
    try:
        assert g.pliki("2021", None)["razem"] == 1
        assert {a for a, _ in g.aparaty()["aparaty"]} == {"Canon EOS", "Samsung"}  # lista bez filtra aparatu
    finally:
        galeria._FILTR.aparat = None
    galeria._FILTR.pora = "noc"
    try:
        assert g.pliki("2021", None)["razem"] == 1
    finally:
        galeria._FILTR.pora = ""


def test_eksport_nazwy_exif(tmp_path):
    k, g = _galeria(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    pl = g.pliki("2021", None)["pliki"]
    id0 = next(p["id"] for p in pl if p["nazwa"] == "S_0.jpg")
    w = g.eksportuj(id0, str(out), 600, 85, True, "© Test")
    with Image.open(w["plik"]) as im:
        assert max(im.size) == 600 and not im.getexif().get(0x8825)
    d = g.wlasciwosci(id0)
    assert d["exif"]["przyslona"] == "f/2.8" and d["exif"]["iso"] == 400 and len(d["histogram"]["l"]) == 64
    n = g.nazwy_podglad([id0], "{data}_{nr}", 1)["nazwy"][0]
    assert n["nowa"] == "2021-07-14_001.jpg" and not n["konflikt"]
    g.album_nowy("A", [id0])
    assert g.zmien_nazwe(id0, "nowa")["nazwa"] == "nowa.jpg" and (k / "nowa.jpg").is_file()
    assert g.kolekcja("album", g.albumy()["albumy"][0]["id"])["pliki"][0]["nazwa"] == "nowa.jpg"
    assert "blad" in g.zmien_nazwe(id0, "S_1")  # taka nazwa już jest
    assert "blad" in g.zmien_nazwe(id0, "a/b")
    assert not os.path.exists(k / "S_0.jpg")
