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
    from PIL import Image
    (a / "Windows" / "Web").mkdir(parents=True)
    _jpg_z_exif(a / "Windows" / "Web" / "tapeta.jpg", data="2020:01:01 10:00:00", gps=None)  # folder systemu: pomijany
    Image.new("RGBA", (32, 32), (0, 90, 200, 255)).save(a / "ikona.png")  # drobna grafika bez daty: nie na osi czasu
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


def test_wyszukiwarka(biblioteka):
    tmp, db, cel = biblioteka
    g = galeria.Galeria(tmp / "k.db")
    nazwy = lambda q: sorted(p["nazwa"] for p in g.szukaj(q)["pliki"])
    assert nazwy("Hel") == ["IMG_20230711.jpg"] and g.szukaj("hel")["opis"] == "Hel"
    assert nazwy("olkusz 2023") == ["IMG_20230310.jpg"]
    assert nazwy("2023") == ["IMG_20230310.jpg", "IMG_20230711.jpg"]
    assert nazwy("lipiec") == ["IMG_20230711.jpg"] and g.szukaj("lipca 2023")["opis"] == "lipiec 2023"
    assert nazwy("20220105") == ["IMG_20220105.jpg"]          # fragment nazwy pliku
    assert nazwy("Polska") == ["IMG_20230310.jpg", "IMG_20230711.jpg"]
    assert nazwy("Włochy") == [] and g.szukaj("")["razem"] == 0


def test_obszar_z_mapy_i_tego_dnia(biblioteka):
    tmp, db, cel = biblioteka
    g = galeria.Galeria(tmp / "k.db")
    hel = (54.5, 54.7, 18.7, 18.9)
    assert [(x["rok"], x["n"]) for x in g.lata(hel)["lata"]] == [("2023", 1)]
    assert [p["nazwa"] for p in g.pliki("2023", None, obszar=hel)["pliki"]] == ["IMG_20230711.jpg"]
    t = g.tego_dnia("07-11")
    assert t["razem"] == 1 and t["lata"] == [{"rok": "2023", "n": 1}]
    assert g.tego_dnia("12-24")["razem"] == 0


def test_ulubione_i_albumy(biblioteka):
    tmp, db, cel = biblioteka
    g = galeria.Galeria(tmp / "k.db")
    ids = {p["nazwa"]: p["id"] for p in g.szukaj("20")["pliki"]}
    hel, olk = ids["IMG_20230711.jpg"], ids["IMG_20230310.jpg"]
    assert g.ulubione(hel) == {"ulubione": True} and g.plik(hel)["ulubione"]
    assert [p["nazwa"] for p in g.kolekcja("ulubione")["pliki"]] == ["IMG_20230711.jpg"]
    a = g.album_nowy("  Wakacje   2023 ", [hel, olk])
    assert a["nazwa"] == "Wakacje 2023" and a["dodane"] == 2
    assert g.albumy()["albumy"][0]["n"] == 2 and g.albumy()["ulubione"]["n"] == 1
    assert g.plik(olk)["albumy"] == [a["id"]]
    g.album_usun_pliki(a["id"], [olk])
    assert [p["nazwa"] for p in g.kolekcja("album", a["id"])["pliki"]] == ["IMG_20230711.jpg"]
    assert g.album_nazwa(a["id"], "Hel")["nazwa"] == "Hel"
    g.album_usun(a["id"])
    assert g.albumy()["albumy"] == [] and (tmp / "dysk" / "IMG_20230711.jpg").exists()  # zdjęcia zostają
    assert g.ulubione(hel) == {"ulubione": False}
    # telefon (serwer tylko do odczytu) nie zmienia kolekcji — obsługa POST jest tylko w oknie programu
    assert galeria.obsluz_post(g, "/api/g/nieznane", {}) is None


def test_miniatura_filmu_z_okna(tmp_path):
    from datetime import datetime, timezone
    from test_katalogator import _mp4
    k = tmp_path / "d"
    k.mkdir()
    _mp4(k / "VID_20230711_120000.mp4", datetime(2023, 7, 11, 12, tzinfo=timezone.utc))
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    g = galeria.Galeria(tmp_path / "k.db")
    fid = g.pliki("2023", None)["pliki"][0]["id"]
    assert g.miniatura(fid) is None
    import base64
    jpg = b"\xff\xd8" + b"x" * 100 + b"\xff\xd9"
    assert galeria.obsluz_post(g, "/api/g/miniatura-filmu", {"id": fid, "jpg": "data:image/jpeg;base64," +
                                                              base64.b64encode(jpg).decode()}) == {"ok": True}
    assert g.miniatura(fid) == jpg
    assert galeria.obsluz_post(g, "/api/g/miniatura-filmu", {"id": fid, "jpg": base64.b64encode(b"<svg>").decode()})["blad"]


def test_przegladarka_samo_odswieza(tmp_path):
    import time
    from katalogator import przegladarka
    p = przegladarka.Przegladarka(tmp_path / "dane")
    assert not p.do_odswiezenia()                     # brak folderów
    (tmp_path / "a").mkdir()
    p.ustaw_foldery([str(tmp_path / "a")])
    assert p.do_odswiezenia()                          # nigdy nie skanowano
    p.skanuj()
    for _ in range(100):
        if not p.opis()["trwa"]:
            break
        time.sleep(0.05)
    assert not p.do_odswiezenia() and p.do_odswiezenia(time.time() + 7 * 3600)
    p.ustaw_auto(False)
    assert not p.do_odswiezenia(time.time() + 99 * 3600) and p.opis()["auto"] is False
