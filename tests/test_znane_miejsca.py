"""📍 znane miejsca z biblioteki — do wyboru przy zmianie lokalizacji."""
from PIL import Image

from katalogator import galeria, skaner


def _gps(lat, lon, d="2022:05:01 12:00:00"):
    e = Image.Exif()
    e[0x8769] = {0x9003: d}
    st = lambda x: (float(int(x)), float(int(x * 60 % 60)), round(x * 3600 % 60, 2))
    e[0x8825] = {1: "N", 2: st(lat), 3: "E", 4: st(lon)}
    return e


def test_znane_miejsca(tmp_path):
    k = tmp_path / "z"
    k.mkdir()
    for i in range(3):  # Kraków — dwa punkty w mieście, jedna grupa
        Image.new("RGB", (64, 64)).save(k / f"kr{i}.jpg", exif=_gps(50.0614 + (i == 2) * 0.01, 19.9366))
    Image.new("RGB", (64, 64)).save(k / "rzym.jpg", exif=_gps(41.9028, 12.4964, "2023:08:10 10:00:00"))
    Image.new("RGB", (64, 64)).save(k / "bez.jpg")
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    db.close()
    galeria._FILTR.okno = True
    m = galeria.Galeria(tmp_path / "k.db").znane_miejsca()["miejsca"]
    assert [x["n"] for x in m] == [3, 1]
    assert m[0]["nazwa"] == "Kraków" and abs(m[0]["lat"] - 50.061) < 0.001
    assert m[1]["nazwa"] == "Włochy" and m[1]["data"] == "2023-08-10"


def test_to_samo_miejsce_rozne_lata(tmp_path):
    k = tmp_path / "z"
    k.mkdir()
    for i, rok in enumerate((2015, 2019, 2019, 2023)):  # rynek w Krakowie
        Image.new("RGB", (64, 64)).save(k / f"r{i}.jpg", exif=_gps(50.0617 + i * 0.0003, 19.9373, f"{rok}:06:0{i + 1} 12:00:00"))
    Image.new("RGB", (64, 64)).save(k / "daleko.jpg", exif=_gps(50.0900, 19.9373, "2020:01:01 10:00:00"))  # ~3 km
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    db.close()
    galeria._FILTR.okno = True
    g = galeria.Galeria(tmp_path / "k.db")
    w = g.to_samo_miejsce(50.0617, 19.9373, 300)
    assert w["razem"] == 4 and w["nazwa"] == "Kraków"
    assert [x["rok"] for x in w["lata"]] == ["2023", "2019", "2015"]
    assert [x["data"][:4] for x in w["pliki"]] == ["2023", "2019", "2019", "2015"]
    assert g.to_samo_miejsce(50.0617, 19.9373, 5000)["razem"] == 5
    m = g.znane_miejsca()["miejsca"]
    assert m[0]["nazwa"] == "Kraków" and m[0]["lat_n"] == 4
    w2, _ = galeria.obsluz_api(g, "/api/g/to-samo-miejsce", {"lat": ["50.0617"], "lon": ["19.9373"], "pr": ["100"]}, okno=True)
    assert w2["r"] == 100 and 1 <= w2["razem"] < 4
