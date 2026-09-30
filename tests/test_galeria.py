"""Przeglądarka biblioteki (oś czasu, mapa) i serwer dla telefonu (PIN, tylko odczyt)."""
import json
import urllib.error
import urllib.request

import pytest

from katalogator import galeria, planista, skaner, wykonawca
from test_katalogator import _jpg_z_exif

OLKUSZ, HEL = (50.2811, 19.5625), (54.6080, 18.8010)


@pytest.fixture
def biblioteka(tmp_path):
    k = tmp_path / "dysk"
    k.mkdir()
    _jpg_z_exif(k / "IMG_20230310.jpg", data="2023:03:10 12:00:00", gps=OLKUSZ)
    _jpg_z_exif(k / "IMG_20230711.jpg", data="2023:07:11 12:00:00", gps=HEL)
    _jpg_z_exif(k / "IMG_20220105.jpg", data="2022:01:05 12:00:00", gps=None)
    cel = tmp_path / "Biblioteka"
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    planista.generuj(db, [{"sciezka": str(k), "tryb": "kopiuj"}], str(cel), dom="Olkusz")
    return tmp_path, db, cel


def test_uporzadkowane_pliki_od_razu_w_bibliotece(biblioteka):
    tmp, db, cel = biblioteka
    g = galeria.Galeria(tmp / "k.db", lambda: [str(cel)])
    assert g.lata()["razem"] == 0  # przed porządkowaniem biblioteka jest pusta
    wykonawca.wykonaj(db)
    l = g.lata()
    assert [(x["rok"], x["n"]) for x in l["lata"]] == [("2023", 2), ("2022", 1)] and l["z_gps"] == 2
    assert len(g.mapa()["punkty"]) == 2
    p = g.pliki("2023", 7)["pliki"]
    assert len(p) == 1 and p[0]["nazwa"] == "IMG_20230711.jpg"
    assert g.plik(p[0]["id"])["miejsce"] == "Hel"
    assert g.miniatura(p[0]["id"], srednia=True)[:2] == b"\xff\xd8"
    # „wszystko w projekcie” = źródła + biblioteka
    assert galeria.Galeria(tmp / "k.db").lata()["razem"] == 6
    # cofnięcie porządkowania: pliki znikają z biblioteki
    wykonawca.cofnij(db)
    assert g.lata()["razem"] == 0


def test_plik_spoza_zakresu_niedostepny(biblioteka):
    tmp, db, cel = biblioteka
    g = galeria.Galeria(tmp / "k.db", lambda: [str(cel)])
    zrodlowy = db.execute("SELECT rowid FROM pliki").fetchone()[0]
    assert g.plik(zrodlowy) is None and g.miniatura(zrodlowy) is None and g.sciezka(zrodlowy) is None


def test_pliki_ui_tylko_z_katalogu_ui():
    assert galeria.plik_ui("/ui/mapa/leaflet.js")[1].startswith("text/javascript")
    assert galeria.plik_ui("/ui/galeria.html")
    for zle in ("/ui/../galeria.py", "/ui/mapa/../../aplikacja.py", "/ui/", "/ui/nie-ma.js"):
        assert galeria.plik_ui(zle) is None


def test_serwer_telefonu_pin(biblioteka):
    tmp, db, cel = biblioteka
    wykonawca.wykonaj(db)
    s = galeria.SerwerGalerii(galeria.Galeria(tmp / "k.db", lambda: [str(cel)]), port=0, pin="2468",
                              host="127.0.0.1").start()
    b = f"http://127.0.0.1:{s.port}"
    try:
        assert b"Biblioteka" in urllib.request.urlopen(b + "/").read()
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(b + "/api/g/lata")
        assert e.value.code == 401

        def zaloguj(pin):
            r = urllib.request.Request(b + "/api/g/zaloguj", data=json.dumps({"pin": pin}).encode(),
                                       headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(r).read())
        with pytest.raises(urllib.error.HTTPError):
            zaloguj("0000")
        t = zaloguj("2468")["t"]
        l = json.loads(urllib.request.urlopen(f"{b}/api/g/lata?t={t}").read())
        assert l["razem"] == 3
        with pytest.raises(urllib.error.HTTPError) as e:  # tylko odczyt: brak innych POST-ów
            urllib.request.urlopen(urllib.request.Request(f"{b}/api/g/lata?t={t}", data=b"{}"))
        assert e.value.code == 404
    finally:
        s.stop()


def test_blokada_po_wielu_zlych_pinach(biblioteka, monkeypatch):
    tmp, db, cel = biblioteka
    monkeypatch.setattr(galeria.time, "sleep", lambda s: None)
    s = galeria.SerwerGalerii(galeria.Galeria(tmp / "k.db"), port=0, pin="2468", host="127.0.0.1").start()
    b = f"http://127.0.0.1:{s.port}"
    kody = []
    try:
        for pin in ["1"] * 8 + ["2468"]:
            r = urllib.request.Request(b + "/api/g/zaloguj", data=json.dumps({"pin": pin}).encode())
            try:
                urllib.request.urlopen(r)
                kody.append(200)
            except urllib.error.HTTPError as e:
                kody.append(e.code)
    finally:
        s.stop()
    assert kody[:8] == [401] * 8 and kody[8] == 429  # nawet dobry PIN czeka, gdy ktoś zgaduje


def test_pusty_zakres_to_pusta_biblioteka(biblioteka):
    tmp, db, cel = biblioteka
    assert galeria.Galeria(tmp / "k.db", lambda: []).lata()["razem"] == 0
    assert galeria.Galeria(tmp / "k.db", lambda: None).lata()["razem"] == 3


def test_przegladarka_dyskow(tmp_path):
    """Przeglądarka: wybrane foldery tylko skanowane (osobna baza), oś czasu i mapa; usunięty z listy znika."""
    import time
    from katalogator import przegladarka
    a, b = tmp_path / "dyskA", tmp_path / "dyskB"
    a.mkdir(); b.mkdir()
    _jpg_z_exif(a / "IMG_1.jpg", data="2021:05:01 10:00:00", gps=HEL)
    _jpg_z_exif(b / "IMG_2.jpg", data="2019:02:01 10:00:00", gps=None)
    przed = {p: p.stat().st_mtime for p in tmp_path.rglob("*.jpg")}
    p = przegladarka.Przegladarka(tmp_path / "dane")
    assert p.skanuj() == "Najpierw dodaj dysk albo folder."
    assert p.ustaw_foldery([str(a), str(b), str(a)]) == sorted([str(a), str(b)], key=len)
    assert p.skanuj() is None
    for _ in range(200):
        if not p.opis()["trwa"]:
            break
        time.sleep(0.05)
    s = p.opis()
    assert not s["trwa"] and s["komunikat"].startswith("Gotowe") and not s["blad"]
    l = p.galeria.lata()
    assert [(x["rok"], x["n"]) for x in l["lata"]] == [("2021", 1), ("2019", 1)] and l["z_gps"] == 1
    assert len(p.galeria.mapa()["punkty"]) == 1
    p.ustaw_foldery([str(a)])  # dysk B usunięty z przeglądarki — jego zdjęcia znikają z osi czasu
    assert [x["rok"] for x in p.galeria.lata()["lata"]] == ["2021"]
    assert {q: q.stat().st_mtime for q in tmp_path.rglob("*.jpg")} == przed  # nic nie zmienione
    # projekt porządkowania nie jest dotknięty
    assert not list((tmp_path / "dane").glob("projekty"))
