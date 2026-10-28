"""👤 Osoby: grupowanie twarzy (bez modeli) i pełne wykrywanie (gdy są OpenCV i modele)."""
import os
import shutil
import time
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from katalogator import galeria, skaner, twarze  # noqa: E402


def _wektor(baza, szum=0.0, ziarno=0):
    r = np.random.default_rng(ziarno)
    v = baza + r.normal(0, szum, 128)
    return (v / np.linalg.norm(v)).astype(np.float32).tobytes()


def test_grupowanie_laczy_podobne_i_rozdziela_rozne(tmp_path):
    db = twarze.otworz_baze(tmp_path / "k.db")
    r = np.random.default_rng(1)
    a, b = r.normal(size=128), r.normal(size=128)
    for i in range(4):
        db.execute("INSERT INTO g_twarze (sciezka, wektor) VALUES (?, ?)", (f"a{i}.jpg", _wektor(a, 0.15, i)))
        db.execute("INSERT INTO g_twarze (sciezka, wektor) VALUES (?, ?)", (f"b{i}.jpg", _wektor(b, 0.15, 10 + i)))
    assert twarze.grupuj(db) == 8
    grupy = {}
    for sc, o in db.execute("SELECT sciezka, osoba FROM g_twarze"):
        grupy.setdefault(o, set()).add(sc[0])
    assert sorted("".join(sorted(g)) for g in grupy.values()) == ["a", "b"]
    # nowa twarz osoby A trafia do istniejącej osoby, odłączona ręcznie — zostaje bez osoby
    db.execute("INSERT INTO g_twarze (sciezka, wektor) VALUES ('a9.jpg', ?)", (_wektor(a, 0.15, 99),))
    db.execute("INSERT INTO g_twarze (sciezka, wektor, reczna) VALUES ('x.jpg', ?, 1)", (_wektor(a, 0.15, 98),))
    twarze.grupuj(db)
    oa = db.execute("SELECT osoba FROM g_twarze WHERE sciezka='a0.jpg'").fetchone()[0]
    assert db.execute("SELECT osoba FROM g_twarze WHERE sciezka='a9.jpg'").fetchone()[0] == oa
    assert db.execute("SELECT osoba FROM g_twarze WHERE sciezka='x.jpg'").fetchone()[0] is None


MODELE = Path(os.environ.get("KATALOGATOR_MODELE", "/tmp/claude-0/modele"))
ZDJECIA = [Path(os.environ.get("KATALOGATOR_TWARZE", "/tmp/claude-0")) / n for n in ("lena.jpg", "messi5.jpg")]


@pytest.mark.skipif(twarze.dostepne() is not None or not (MODELE / twarze.MODEL_ROZPOZNAWANIA).is_file()
                    or not all(p.is_file() for p in ZDJECIA), reason="brak OpenCV, modelu lub zdjęć z twarzami")
def test_wykrywanie_osoby_nazwa_szukanie(tmp_path, monkeypatch):
    from PIL import Image
    monkeypatch.setattr(twarze, "KATALOG_MODELI", MODELE)
    k = tmp_path / "zdj"
    k.mkdir()
    shutil.copy(ZDJECIA[0], k / "lena1.jpg")
    Image.open(ZDJECIA[0]).transpose(Image.FLIP_LEFT_RIGHT).resize((400, 400)).save(k / "lena2.jpg")
    im = Image.open(ZDJECIA[1]); im.resize((im.width * 2, im.height * 2)).save(k / "messi.jpg")  # twarz > MIN_TWARZ
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    db.close()
    g = galeria.Galeria(tmp_path / "k.db")
    assert twarze.start(g) is None
    for _ in range(300):
        if not twarze.stan(g.baza).get("trwa"):
            break
        time.sleep(0.1)
    s = twarze.stan(g.baza)
    assert not s.get("blad") and s["zrobione"] == 3 and s["twarzy"] >= 3
    o = twarze.osoby(g)
    assert o["przejrzane"] == 3
    lena = next(x for x in o["osoby"] if x["n"] == 2)  # dwa zdjęcia Leny = jedna osoba
    assert twarze.miniatura_twarzy(g, lena["twarz"]).startswith(b"\xff\xd8")
    twarze.nazwij(g, lena["id"], "Lena")
    assert {p["nazwa"] for p in g.osoba(lena["id"])["pliki"]} == {"lena1.jpg", "lena2.jpg"}
    w = g.szukaj("lena")
    assert w["razem"] == 2 and "Lena" in w["opis"]
    # ponowne uruchomienie nie przegląda drugi raz tych samych zdjęć
    twarze.start(g)
    for _ in range(100):
        if not twarze.stan(g.baza).get("trwa"):
            break
        time.sleep(0.1)
    assert twarze.stan(g.baza)["wszystkie"] == 0
    # ⚙ zmiana silnika na dokładniejszy (InsightFace buffalo_l): zdjęcia od nowa, imię zostaje przy osobie
    if not twarze.model_pobrany("arcface"):
        return
    monkeypatch.setattr(twarze, "SILNIK", "arcface")
    if twarze.dostepne():
        return
    twarze.start(g)
    for _ in range(600):
        if not twarze.stan(g.baza).get("trwa"):
            break
        time.sleep(0.1)
    s = twarze.stan(g.baza)
    assert not s.get("blad") and s["zrobione"] == 3
    db = twarze.otworz_baze(tmp_path / "k.db")
    assert {r[0] for r in db.execute("SELECT DISTINCT length(wektor) FROM g_twarze")} == {512 * 4}  # stare znikły
    o = twarze.osoby(g)
    lena2 = next(x for x in o["osoby"] if x["nazwa"] == "Lena")
    assert {p["nazwa"] for p in g.osoba(lena2["id"])["pliki"]} == {"lena1.jpg", "lena2.jpg"}
    assert twarze.miniatura_twarzy(g, lena2["twarz"]).startswith(b"\xff\xd8")  # okładka wskazuje nową twarz
    messi = db.execute("SELECT osoba FROM g_twarze WHERE sciezka LIKE '%messi.jpg'").fetchone()[0]
    assert messi != lena2["id"]


def test_pobieranie_modeli_buffalo_sprawdza_sumy(tmp_path, monkeypatch):
    """Paczka buffalo_l: rozpakowujemy tylko 2 potrzebne modele i sprawdzamy ich sumy; zła suma = nic nie zostaje."""
    import hashlib
    import zipfile
    paczka = tmp_path / "buffalo_l.zip"
    with zipfile.ZipFile(paczka, "w") as z:
        z.writestr("det_10g.onnx", b"wykrywanie")
        z.writestr("w600k_r50.onnx", b"rozpoznawanie")
        z.writestr("1k3d68.onnx", b"niepotrzebny")
    monkeypatch.setattr(twarze, "URL_BUFFALO", paczka.as_uri())
    monkeypatch.setattr(twarze, "KATALOG_MODELI", tmp_path / "modele")
    with pytest.raises(OSError):
        twarze.pobierz_buffalo()
    assert not twarze.model_pobrany("arcface") and not list((tmp_path / "modele" / "buffalo_l").glob("*.zip*"))
    monkeypatch.setattr(twarze, "PLIKI_BUFFALO", {n: hashlib.sha256(b).hexdigest() for n, b in
                                                 (("det_10g.onnx", b"wykrywanie"), ("w600k_r50.onnx", b"rozpoznawanie"))})
    kat = twarze.pobierz_buffalo()
    assert twarze.model_pobrany("arcface") and sorted(p.name for p in kat.iterdir()) == ["det_10g.onnx", "w600k_r50.onnx"]
