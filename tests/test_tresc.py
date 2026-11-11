"""🧠 Wyszukiwanie po treści: integracja z wyszukiwarką Przeglądarki (model zastąpiony prostym „koderem”)."""
import numpy as np

from katalogator import galeria, skaner, tresc
from test_katalogator import _jpg_z_exif


def _wektor(i):
    v = np.zeros(512, np.float32)
    v[i] = 1.0
    return v


def test_szukanie_po_tresci_razem_z_rokiem(tmp_path, monkeypatch):
    k = tmp_path / "zdj"
    k.mkdir()
    for n, d in (("a.jpg", "2023:07:01 12:00:00"), ("b.jpg", "2023:07:02 12:00:00"), ("c.jpg", "2019:01:01 12:00:00"),
                 ("slonecznik_nazwa.jpg", "2020:05:05 12:00:00")):
        _jpg_z_exif(k / n, data=d, gps=None)
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    db.close()
    monkeypatch.setattr(tresc, "KATALOG_MODELI", tmp_path / "modele")
    monkeypatch.setattr(tresc, "pobrany", lambda: True)
    monkeypatch.setattr(tresc, "PROG", 0.5)
    monkeypatch.setattr(tresc, "ODSTEP", 0.5)
    w = tresc._baza()   # „plaża” = oś 0: a.jpg i c.jpg wyglądają jak plaża, b.jpg nie
    for n, v in (("a.jpg", _wektor(0)), ("b.jpg", _wektor(1)), ("c.jpg", _wektor(0) * 0.9 + _wektor(1) * 0.1)):
        w.execute("INSERT INTO g_clip VALUES (?,?,?)", (str(k / n), 0, (v / np.linalg.norm(v)).astype(np.float16).tobytes()))
    w.commit(); w.close()
    tresc._pamiec.clear()
    monkeypatch.setattr(tresc, "wektor_tekstu", lambda t: _wektor(0))
    g = galeria.Galeria(tmp_path / "k.db", lambda: [str(k)])
    r = g.szukaj("slonecznik")
    nazwy = [p["nazwa"] for p in r["pliki"]]
    assert "a.jpg" in nazwy and "c.jpg" in nazwy and "b.jpg" not in nazwy
    assert "🧠" in r["opis"]
    r = g.szukaj("slonecznik 2023")                       # treść + rok
    assert [p["nazwa"] for p in r["pliki"]] == ["a.jpg"]
    r = g.szukaj("slonecznik")                            # trafienie w nazwie pliku jest pierwsze
    assert r["pliki"][0]["nazwa"] == "slonecznik_nazwa.jpg"


def test_bez_modelu_zwykle_wyszukiwanie(tmp_path, monkeypatch):
    k = tmp_path / "zdj"
    k.mkdir()
    _jpg_z_exif(k / "slonecznik.jpg", data="2020:05:05 12:00:00", gps=None)
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    db.close()
    monkeypatch.setattr(tresc, "KATALOG_MODELI", tmp_path / "modele")
    g = galeria.Galeria(tmp_path / "k.db", lambda: [str(k)])
    r = g.szukaj("slonecznik")
    assert [p["nazwa"] for p in r["pliki"]] == ["slonecznik.jpg"] and "🧠" not in r["opis"]


def test_ocena_i_tagi_w_bazie_exif_i_wyszukiwaniu(tmp_path):
    from PIL import Image
    k = tmp_path / "zdj"
    k.mkdir()
    _jpg_z_exif(k / "a.jpg", data="2023:07:01 12:00:00", gps=None)
    _jpg_z_exif(k / "b.jpg", data="2023:07:02 12:00:00", gps=None)
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    db.close()
    g = galeria.Galeria(tmp_path / "k.db", lambda: [str(k)])
    ids = {p["nazwa"]: p["id"] for p in g.pliki("2023", 7)["pliki"]}
    assert g.ocen([ids["a.jpg"]], 5, ["Wakacje", "morze"])["w_pliku"] == 1
    g.ocen([ids["b.jpg"]], 2)
    e = Image.open(k / "a.jpg").getexif()
    assert e.get(0x4746) == 5 and bytes(e.get(0x9C9E)).decode("utf-16-le").rstrip("\x00") == "Wakacje;morze"
    assert [p["nazwa"] for p in g.szukaj("★4")["pliki"]] == ["a.jpg"]
    assert {p["nazwa"] for p in g.szukaj("2★")["pliki"]} == {"a.jpg", "b.jpg"}
    assert [p["nazwa"] for p in g.szukaj("#wakacje")["pliki"]] == ["a.jpg"]
    g.ocen([ids["a.jpg"]], None, [], ["morze"])
    assert g.plik(ids["a.jpg"])["tagi"] == ["Wakacje"] and g.plik(ids["a.jpg"])["ocena"] == 5
    assert g.tagi_wszystkie() == ["Wakacje"]
