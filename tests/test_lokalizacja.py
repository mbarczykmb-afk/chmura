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


def test_zmiana_daty_w_pliku_i_po_skanie(tmp_path):
    """📅 JPEG: data w EXIF (obraz bez zmian); PNG: .xmp obok z ręczną datą, która wygrywa przy skanie;
    ręczna lokalizacja i ręczna data w tym samym .xmp nie nadpisują się nawzajem."""
    from PIL import Image
    from test_katalogator import _jpg_z_exif
    from katalogator import galeria, lokalizacja, skaner
    k = tmp_path / "dysk"
    k.mkdir()
    _jpg_z_exif(k / "a.jpg", data="2010:01:01 10:00:00", gps=None)
    Image.new("RGB", (400, 300), (10, 120, 200)).save(k / "b.png")
    piksele = Image.open(k / "a.jpg").tobytes()
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    ids = {r[1]: r[0] for r in db.execute("SELECT rowid, wzgledna FROM pliki")}
    g = galeria.Galeria(tmp_path / "k.db")
    w = g.data([ids["a.jpg"], ids["b.png"]], "2015-06-07T08:09:10")
    assert w["zmienione"] == 2 and not w["bledy"]
    with Image.open(k / "a.jpg") as im:
        assert im.getexif().get_ifd(0x8769)[0x9003] == "2015:06:07 08:09:10"
        assert im.tobytes() == piksele
    assert (k / "b.png.xmp").exists()
    g.lokalizacja([ids["b.png"]], 50.0, 19.0)                     # lokalizacja nie kasuje ręcznej daty
    assert b'katalogator:Data="2015-06-07T08:09:10"' in (k / "b.png.xmp").read_bytes()
    db.execute("DELETE FROM pliki")
    db.commit()
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)            # od nowa z dysku
    daty = {r[0]: (r[1], r[2]) for r in db.execute("SELECT wzgledna, data, lat FROM pliki WHERE rodzaj='zdjecie'")}
    assert daty["a.jpg"][0].startswith("2015-06-07T08:09:10")
    assert daty["b.png"][0].startswith("2015-06-07T08:09:10") and daty["b.png"][1] == 50.0
    assert lokalizacja.ustaw_date(db, [1], "zła data")["blad"]


def test_oznacz_dokument_i_filtr(tmp_path):
    from test_katalogator import _jpg_z_exif
    from katalogator import galeria, skaner
    k = tmp_path / "dysk"
    (k / "Dokumenty z 2020").mkdir(parents=True)
    _jpg_z_exif(k / "zwykle.jpg", data="2020:01:01 10:00:00", gps=None)
    _jpg_z_exif(k / "Dokumenty z 2020" / "skan.jpg", data="2020:01:02 10:00:00", gps=None)
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    ids = {r[1].replace("\\", "/"): r[0] for r in db.execute("SELECT rowid, wzgledna FROM pliki")}
    g = galeria.Galeria(tmp_path / "k.db")

    def lista(r):
        galeria.obsluz_api(g, "/api/g/lata", {"r": [r]})  # ustawia filtr na czas zapytania
        return sorted(p["nazwa"] for p in g.pliki("2020", None)["pliki"])
    assert lista("dokument") == ["skan.jpg"]
    galeria.obsluz_post(g, "/api/g/dokument", {"ids": [ids["zwykle.jpg"]], "tak": True})
    galeria.obsluz_post(g, "/api/g/dokument", {"ids": [ids["Dokumenty z 2020/skan.jpg"]], "tak": False})
    assert lista("dokument") == ["zwykle.jpg"] and lista("zdjecie") == ["skan.jpg"]
    assert galeria.obsluz_api(g, "/api/g/plik", {"id": [str(ids["zwykle.jpg"])], "r": ["zdjecie"]})[0]["dokument"] is True
    galeria.obsluz_api(g, "/api/g/lata", {})
