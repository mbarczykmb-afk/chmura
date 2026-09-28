import json
import os

from katalogator import dyski
from test_aplikacja import app  # noqa: F401  (fikstura)


def test_normalizuj_wybor(tmp_path):
    a, b, c = str(tmp_path / "A"), str(tmp_path / "A" / "B"), str(tmp_path / "AB")
    w = dyski.normalizuj_wybor([{"sciezka": b, "tryb": "przenies"}, a, {"sciezka": c, "tryb": "przenies"},
                                {"sciezka": a + os.sep, "tryb": "przenies"}, " ", {"sciezka": c, "tryb": "zly"}])
    # a: ostatni wpis wygrywa (przenieś); b zawarte w a; c: nieznany tryb -> kopiuj
    assert w == [{"sciezka": a, "tryb": "przenies"}, {"sciezka": c, "tryb": "kopiuj"}]
    assert dyski.zawiera(a, b) and not dyski.zawiera(a, c) and dyski.zawiera(a, a)


def test_podfoldery_pomija_ukryte_i_smieci(tmp_path):
    for n in ("Zdjęcia", "muzyka", ".ukryty", ".wdmc", "$RECYCLE.BIN", "_Duplikaty_Katalogator"):
        (tmp_path / n).mkdir()
    (tmp_path / "plik.txt").write_text("x")
    r = dyski.podfoldery(str(tmp_path))
    assert [f["nazwa"] for f in r["foldery"]] == ["muzyka", "Zdjęcia"]
    assert r["foldery"][1]["sciezka"] == str(tmp_path / "Zdjęcia")


def test_podfoldery_blad(tmp_path):
    r = dyski.podfoldery(str(tmp_path / "nie_ma"))
    assert r["foldery"] == [] and r["blad"]


def test_nowy_folder(tmp_path):
    assert dyski.nowy_folder(str(tmp_path), "Uporządkowane")["sciezka"] == str(tmp_path / "Uporządkowane")
    assert (tmp_path / "Uporządkowane").is_dir()
    assert "blad" in dyski.nowy_folder(str(tmp_path), "Uporządkowane")
    assert "blad" in dyski.nowy_folder(str(tmp_path), "zła/nazwa")
    assert "blad" in dyski.nowy_folder(str(tmp_path), "..")


def test_api_drzewa(app, tmp_path):  # noqa: F811
    api, _, _ = app
    d = json.loads(api("/api/dyski")[1])["dyski"]
    assert d and all("sciezka" in x for x in d)
    (tmp_path / "Z" / "Zdjęcia").mkdir(parents=True)
    from urllib.parse import quote
    r = json.loads(api("/api/foldery?sciezka=" + quote(str(tmp_path / "Z")))[1])
    assert [f["nazwa"] for f in r["foldery"]] == ["Zdjęcia"]
    w = json.loads(api("/api/nowy-folder", {"w": str(tmp_path / "Z"), "nazwa": "Cel"})[1])
    assert os.path.isdir(w["sciezka"])
    # rodzic zaznaczony razem z dzieckiem -> zostaje tylko rodzic
    s = json.loads(api("/api/ustawienia", {"zrodla": [
        {"sciezka": str(tmp_path / "Z" / "Zdjęcia"), "tryb": "kopiuj"},
        {"sciezka": str(tmp_path / "Z"), "tryb": "przenies"}]})[1])
    assert s["zrodla"] == [{"sciezka": str(tmp_path / "Z"), "tryb": "przenies"}]


def test_stary_plik_ustawien(tmp_path):
    from katalogator.aplikacja import Stan
    (tmp_path / "ustawienia.json").write_text('{"zrodla": ["Z:/Zdjecia"], "cel": ""}', encoding="utf-8")
    st = Stan(tmp_path)
    assert st.ustawienia["zrodla"] == [{"sciezka": os.path.normpath("Z:/Zdjecia"), "tryb": "kopiuj"}]
