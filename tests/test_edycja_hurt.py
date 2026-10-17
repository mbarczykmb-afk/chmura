"""✏ Hurtem: obrót z zastąpieniem oryginału i ✨ Auto liczone przez program."""
from PIL import Image

from katalogator import edycja, galeria, skaner


def _exif(d):
    e = Image.Exif()
    e[0x8769] = {0x9003: d}
    return e


def test_obrot_zastepuje_oryginal_i_cofanie(tmp_path):
    k = tmp_path / "zdj"
    k.mkdir()
    Image.new("RGB", (400, 300), (200, 100, 50)).save(k / "a.jpg", exif=_exif("2021:05:01 12:00:00"))
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    db.close()
    g = galeria.Galeria(tmp_path / "k.db")
    id_ = g.lata()["lata"] and g.pliki("2021", None)["pliki"][0]["id"]
    w = g.edytuj(id_, {"obrot": 90}, zastap=True)
    assert w.get("ok") and w["nazwa"] == "a.jpg"
    with Image.open(k / "a.jpg") as im:
        assert im.size == (300, 400)
    assert g.edytuj_cofnij(w["id"], w["partia"])["przywrocone"] == 1
    with Image.open(k / "a.jpg") as im:
        assert im.size == (400, 300)


def test_auto_zmienia_i_ma_rozsadne_wartosci():
    op = edycja.normalizuj({"auto": True})
    assert edycja.zmienia(op)
    a = edycja.auto_ustawienia(Image.new("RGB", (64, 64), (60, 60, 120)))  # ciemne, niebieskawe
    assert a["jasnosc"] > 0 and a["temperatura"] > 0  # rozjaśnij i ociepl
