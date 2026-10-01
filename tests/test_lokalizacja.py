"""📍 Edycja lokalizacji: JPEG — EXIF w pliku bez ponownego kodowania; inne — .xmp obok; usuwanie; ponowny skan."""

import os

from PIL import Image

from katalogator import galeria, lokalizacja, metadane, skaner
from test_katalogator import _jpg_z_exif

HEL = (54.608, 18.801)


def _obraz(dane: bytes) -> bytes:  # wszystko od danych obrazu (SOS) — musi zostać bajt w bajt
    return dane[dane.index(b"\xff\xda"):]


def test_jpeg_gps_bez_zmiany_obrazu_i_daty(tmp_path):
    k = tmp_path / "d"
    k.mkdir()
    p = k / "a.jpg"
    _jpg_z_exif(p, data="2021:05:01 12:00:00", gps=None)
    os.utime(p, (1_600_000_000, 1_600_000_000))
    przed = p.read_bytes()
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    i = db.execute("SELECT rowid FROM pliki").fetchone()[0]
    w = lokalizacja.ustaw(db, [i], *HEL)
    assert w["zmienione"] == 1 and w["poprzednie"] == {i: [None, None]}
    po = p.read_bytes()
    assert _obraz(po) == _obraz(przed) and os.stat(p).st_mtime == 1_600_000_000
    m = metadane.odczytaj(str(p), "zdjecie", 0)
    assert (round(m.lat, 4), round(m.lon, 4)) == HEL and m.data.year == 2021  # data z EXIF zachowana
    assert db.execute("SELECT lat, lon, rozmiar FROM pliki").fetchone()[:] == (*HEL, len(po))
    with Image.open(p) as im:
        im.load()  # obraz da się zdekodować
    # zmiana i usunięcie
    lokalizacja.ustaw(db, [i], 50.06, 19.94)
    assert round(metadane.odczytaj(str(p), "zdjecie", 0).lat, 2) == 50.06
    lokalizacja.ustaw(db, [i], None, None)
    assert metadane.odczytaj(str(p), "zdjecie", 0).lat is None and _obraz(p.read_bytes()) == _obraz(przed)
    # ponowny skan widzi to samo (bez zmian w bazie)
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    assert db.execute("SELECT lat FROM pliki").fetchone()[0] is None


def test_inne_formaty_przez_xmp_obok(tmp_path):
    k = tmp_path / "d"
    k.mkdir()
    p = k / "b.png"
    Image.new("RGB", (40, 30), (1, 2, 3)).save(p)
    przed = p.read_bytes()
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    i = db.execute("SELECT rowid FROM pliki").fetchone()[0]
    assert lokalizacja.ustaw(db, [i], *HEL)["zmienione"] == 1
    assert p.read_bytes() == przed and (k / "b.png.xmp").exists()
    # nowy projekt (świeży skan) czyta lokalizację z .xmp
    db2 = skaner.otworz_baze(tmp_path / "k2.db")
    skaner.skanuj(str(k), db2, wypisz=lambda *_: None)
    assert db2.execute("SELECT round(lat, 3), round(lon, 3) FROM pliki WHERE sciezka LIKE '%.png'").fetchone()[:] == HEL
    # usunięcie: znacznik „brak” wygrywa także z plikiem .json Google obok
    (k / "b.png.json").write_text('{"geoData": {"latitude": 50.1, "longitude": 19.1}}')
    lokalizacja.ustaw(db, [i], None, None)
    m = metadane.Metadane()
    metadane.z_bocznych([str(k / "b.png.json"), str(k / "b.png.xmp")], m)
    assert m.lat is None


def test_cudzy_xmp_nie_nadpisany(tmp_path):
    k = tmp_path / "d"
    k.mkdir()
    Image.new("RGB", (40, 30)).save(k / "c.png")
    (k / "c.png.xmp").write_text("<x:xmpmeta>Lightroom</x:xmpmeta>")
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    i = db.execute("SELECT rowid FROM pliki WHERE sciezka LIKE '%c.png'").fetchone()[0]
    w = lokalizacja.ustaw(db, [i], *HEL)
    assert w["zmienione"] == 0 and "innego programu" in w["bledy"][0]
    assert (k / "c.png.xmp").read_text() == "<x:xmpmeta>Lightroom</x:xmpmeta>"


def test_galeria_lokalizacja_w_zakresie(tmp_path):
    k = tmp_path / "d"
    k.mkdir()
    _jpg_z_exif(k / "a.jpg", data="2021:05:01 12:00:00", gps=None)
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    g = galeria.Galeria(tmp_path / "k.db", lambda: [str(k)])
    i = db.execute("SELECT rowid FROM pliki").fetchone()[0]
    assert g.lata()["z_gps"] == 0
    w = galeria.obsluz_post(g, "/api/g/lokalizacja", {"ids": [i], "lat": HEL[0], "lon": HEL[1]})
    assert w["zmienione"] == 1 and g.lata()["z_gps"] == 1
    assert galeria.obsluz_post(g, "/api/g/lokalizacja", {"ids": [i], "lat": None})["zmienione"] == 1
    assert g.lata()["z_gps"] == 0
    assert "blad" in galeria.Galeria(tmp_path / "k.db", lambda: [str(tmp_path / "inny")]).lokalizacja([i], 1, 1)
