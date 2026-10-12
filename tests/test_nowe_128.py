"""1.28: edycja zdjęć, ZIP, udostępnianie albumu, wysyłanie z telefonu, kopia zapasowa i sprawdzanie plików."""
import io
import json
import os
import threading
import time
import urllib.error
import urllib.request
import zipfile

import pytest
from PIL import Image

from katalogator import aplikacja, edycja, galeria, kopia, pilot, skaner, wysylanie
from test_katalogator import _jpg_z_exif


def _zdjecie(sciezka, rozmiar=(400, 300), kolor=(120, 100, 80), orientacja=None, data="2019:07:14 12:30:00"):
    im = Image.new("RGB", rozmiar, kolor)
    ex = Image.Exif()
    if orientacja:
        ex[0x0112] = orientacja
    ex.get_ifd(0x8769)[0x9003] = data
    im.save(sciezka, exif=ex.tobytes(), quality=95)


@pytest.fixture
def folder(tmp_path):
    k = tmp_path / "zdj"
    k.mkdir()
    _zdjecie(k / "a.jpg", orientacja=6)
    _jpg_z_exif(k / "b.jpg", data="2020:01:02 10:00:00")
    _jpg_z_exif(k / "c.jpg", data="2020:01:03 10:00:00")
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    ids = {r["wzgledna"]: r["rowid"] for r in db.execute("SELECT rowid, wzgledna FROM pliki")}
    db.close()
    return tmp_path, k, ids


# --- ✏ edycja ---------------------------------------------------------------------------------
def test_lut_i_normalizacja():
    op = edycja.normalizuj({"jasnosc": 500, "obrot": 450, "ciecie": [0.9, 0, 0.1, 1], "kontrast": "x"})
    assert op["jasnosc"] == 100 and op["obrot"] == 270 and "ciecie" not in op and op["kontrast"] == 0
    assert not edycja.zmienia(edycja.normalizuj({}))
    l = edycja.lut(edycja.normalizuj({}))
    assert l[:256] == list(range(256))  # bez zmian = tożsamość
    jasniej = edycja.lut(edycja.normalizuj({"jasnosc": 50}))
    assert jasniej[128] > 128 and jasniej[0] == 0 and jasniej[255] == 255
    cieplej = edycja.lut(edycja.normalizuj({"temperatura": 60}))
    assert cieplej[100] > 100 > cieplej[512 + 100]  # więcej czerwieni, mniej niebieskiego


def test_edycja_kopia_obrot_przyciecie_exif(folder):
    tmp, k, ids = folder
    g = galeria.Galeria(tmp / "k.db")
    w = g.edytuj(ids["a.jpg"], {"obrot": 90, "ciecie": [0, 0, 0.5, 1], "jasnosc": 30}, zastap=False)
    assert w["ok"] and w["nazwa"] == "a (edytowane).jpg" and w["plik"]["data"] == "2019-07-14T12:30:00"
    im = Image.open(w["sciezka"])
    # 400×300 z orientacją 6 → pionowe 300×400 → obrót w prawo → 400×300 → lewa połowa 200×300
    assert im.size == (200, 300)
    ex = im.getexif()
    assert ex.get(0x0112) == 1 and ex.get_ifd(0x8769).get(0x9003) == "2019:07:14 12:30:00"
    assert (k / "a.jpg").exists()  # oryginał bez zmian
    druga = g.edytuj(ids["a.jpg"], {"kontrast": 10})
    assert druga["nazwa"] == "a (edytowane) 2.jpg"
    assert g.edytuj_cofnij(w["id"], None)["przywrocone"] == 0 and not os.path.exists(w["sciezka"])
    assert g.edytuj(ids["a.jpg"], {})["blad"]


def test_edycja_zastap_i_cofnij(folder):
    tmp, k, ids = folder
    g = galeria.Galeria(tmp / "k.db")
    przed = (k / "b.jpg").read_bytes()
    w = g.edytuj(ids["b.jpg"], {"nasycenie": 40, "temperatura": 20}, zastap=True)
    assert w["zastapiono"] and w["sciezka"] == str(k / "b.jpg") and w["partia"]
    assert (k / "b.jpg").read_bytes() != przed
    assert any("b.jpg" in f for _, _, pl in os.walk(k / "Odłożone") for f in pl)  # oryginał w koszu programu
    c = g.edytuj_cofnij(w["id"], w["partia"])
    assert c["przywrocone"] == 1 and (k / "b.jpg").read_bytes() == przed


# --- ⬇ ZIP i 🔗 udostępnianie albumu --------------------------------------------------------------
def test_zip_i_udostepniony_album(folder):
    tmp, k, ids = folder
    g = galeria.Galeria(tmp / "k.db")
    a = g.album_nowy("Wakacje", [ids["b.jpg"], ids["c.jpg"]])["id"]
    assert sorted(os.path.basename(x) for x in g.pliki_zip(album=a)) == ["b.jpg", "c.jpg"]
    t = g.udostepnij(a)["token"]
    assert t and g.udostepnij(a)["token"] == t and g.album_tokenu(t) == a
    assert g.albumy()["albumy"][0]["udostepniony"]
    s = galeria.SerwerGalerii(g, port=0, pin="2468", host="127.0.0.1").start()
    b = f"http://127.0.0.1:{s.port}"
    try:
        assert b"album" in urllib.request.urlopen(f"{b}/a/{t}").read().lower()
        lista = json.loads(urllib.request.urlopen(f"{b}/a/{t}/api").read())
        assert lista["nazwa"] == "Wakacje" and len(lista["pliki"]) == 2
        assert urllib.request.urlopen(f"{b}/a/{t}/min?id={ids['b.jpg']}").read()[:2] == b"\xff\xd8"
        with pytest.raises(urllib.error.HTTPError) as e:  # zdjęcie spoza albumu — nie
            urllib.request.urlopen(f"{b}/a/{t}/min?id={ids['a.jpg']}")
        assert e.value.code == 404
        z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(f"{b}/a/{t}/zip").read()))
        assert sorted(z.namelist()) == ["b.jpg", "c.jpg"] and z.read("b.jpg") == (k / "b.jpg").read_bytes()
        with pytest.raises(urllib.error.HTTPError):  # reszta serwera nadal za PIN-em
            urllib.request.urlopen(f"{b}/api/g/lata")
        # ZIP zaznaczonych: klucz z POST (po PIN-ie), pobranie GET
        tok = json.loads(urllib.request.urlopen(urllib.request.Request(
            f"{b}/api/g/zaloguj", data=b'{"pin":"2468"}', headers={"Content-Type": "application/json"})).read())["t"]
        kl = json.loads(urllib.request.urlopen(urllib.request.Request(
            f"{b}/api/g/zip?t={tok}", data=json.dumps({"ids": [ids["a.jpg"], ids["c.jpg"]]}).encode())).read())["klucz"]
        z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(f"{b}/api/g/zip?t={tok}&k={kl}").read()))
        assert sorted(z.namelist()) == ["a.jpg", "c.jpg"]
        g.udostepnij(a, False)
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"{b}/a/{t}/api")
        assert e.value.code == 404
    finally:
        s.stop()


# --- 📤 wysyłanie do biblioteki ---------------------------------------------------------------------
def test_wysylanie_do_biblioteki(tmp_path):
    cel = tmp_path / "Biblioteka"
    cel.mkdir()
    _jpg_z_exif(tmp_path / "z_telefonu.jpg", data="2024:05:17 09:00:00")
    dane = (tmp_path / "z_telefonu.jpg").read_bytes()
    baza = tmp_path / "k.db"
    w = wysylanie.przyjmij(baza, str(cel), "../IMG 1.jpg", 1715929200.0, io.BytesIO(dane), len(dane))
    assert w["ok"] and w["folder"] == os.path.join("Z telefonu", "2024-05") and w["nazwa"] == "IMG 1.jpg"
    assert (cel / "Z telefonu" / "2024-05" / "IMG 1.jpg").read_bytes() == dane
    db = skaner.otworz_baze(baza)
    assert db.execute("SELECT data FROM pliki WHERE rowid=?", (w["id"],)).fetchone()[0] == "2024-05-17T09:00:00"
    db.close()
    again = wysylanie.przyjmij(baza, str(cel), "inna_nazwa.jpg", None, io.BytesIO(dane), len(dane))
    assert again["juz_jest"]  # ta sama zawartość — bez kopii
    assert wysylanie.przyjmij(baza, str(cel), "program.exe", None, io.BytesIO(b"x"), 1)["blad"]
    assert wysylanie.przyjmij(baza, "", "a.jpg", None, io.BytesIO(dane), len(dane))["blad"]
    with pytest.raises(ConnectionError):  # przerwane — bez pozostałości
        wysylanie.przyjmij(baza, str(cel), "x.jpg", None, io.BytesIO(dane[:10]), len(dane))
    assert not [f for f in os.listdir(cel / "Z telefonu") if f.endswith(".part")]


def test_wysylanie_przez_serwer_telefonu(tmp_path):
    """Telefon → serwer telefonu → program (przekazywane strumieniowo) → biblioteka."""
    cel = tmp_path / "Biblioteka"
    cel.mkdir()
    serwer, url, stan2 = aplikacja.uruchom_serwer(tmp_path / "dane")
    threading.Thread(target=serwer.serve_forever, daemon=True).start()
    stan2.ustawienia["cel"] = str(cel)
    stan2.glowny = (serwer.server_address[1], url.split("?t=")[1])
    s = galeria.SerwerGalerii(stan2.galeria("wszystko"), port=0, pin="1357", host="127.0.0.1",
                              pilot=pilot.Pilot(stan2, True), galerie=stan2.galeria).start()
    try:
        b = f"http://127.0.0.1:{s.port}"
        t = json.loads(urllib.request.urlopen(urllib.request.Request(
            f"{b}/api/g/zaloguj", data=b'{"pin":"1357"}', headers={"Content-Type": "application/json"})).read())["t"]
        _jpg_z_exif(tmp_path / "x.jpg", data="2023:02:01 10:00:00")
        dane = (tmp_path / "x.jpg").read_bytes() + b"\0" * (9 * 1024 * 1024)  # > 8 MB: przekazywane kawałkami
        w = json.loads(urllib.request.urlopen(urllib.request.Request(
            f"{b}/api/g/wyslij?nazwa=x.jpg&mtime=0", data=dane,
            headers={"X-Token": t, "Content-Type": "application/octet-stream"})).read())
        assert w["ok"] and (cel / "Z telefonu" / "2023-02" / "x.jpg").exists()
    finally:
        s.stop()
        serwer.shutdown()


# --- 💾 kopia zapasowa i sprawdzanie ----------------------------------------------------------------
def test_kopia_przyrostowa_bez_usuwania(tmp_path):
    bib, kop = tmp_path / "Bib", tmp_path / "Kopia"
    (bib / "2020").mkdir(parents=True)
    (bib / "Odłożone" / "Usunięte").mkdir(parents=True)
    (bib / "2020" / "a.jpg").write_bytes(b"A" * 1000)
    (bib / "b.txt").write_bytes(b"B")
    (bib / "Odłożone" / "Usunięte" / "x.jpg").write_bytes(b"X")
    w = kopia.kopiuj(str(bib), str(kop))
    assert w["skopiowane"] == 2 and (kop / "2020" / "a.jpg").read_bytes() == b"A" * 1000
    assert not (kop / "Odłożone").exists()  # kosz programu nie jest kopiowany
    assert kopia.kopiuj(str(bib), str(kop))["skopiowane"] == 0
    (bib / "b.txt").unlink()
    (bib / "c.jpg").write_bytes(b"C")
    w = kopia.kopiuj(str(bib), str(kop))
    assert w["skopiowane"] == 1 and (kop / "b.txt").exists()  # z kopii nic nie znika
    assert kopia.sprawdz_miejsce(str(bib), str(bib / "kopia"))  # kopia w bibliotece — nie


def test_sprawdzanie_wykrywa_uszkodzenie_i_przywraca(tmp_path):
    bib, kop = tmp_path / "Bib", tmp_path / "Kopia"
    bib.mkdir()
    _zdjecie(bib / "a.jpg")
    (bib / "b.bin").write_bytes(b"0123456789" * 100)
    kopia.kopiuj(str(bib), str(kop))
    db = kopia.baza(tmp_path)
    w = kopia.sprawdz(db, str(bib), str(kop))
    assert w["nowe"] == 2 and w["problemy"] == 0
    assert kopia.sprawdz(db, str(bib), str(kop))["pominiete"] == 2  # sprawdzone niedawno — pomijane
    # „bit rot”: ta sama data i rozmiar, inna zawartość
    st = os.stat(bib / "b.bin")
    with open(bib / "b.bin", "r+b") as f:
        f.seek(50)
        f.write(b"X")
    os.utime(bib / "b.bin", (st.st_atime, st.st_mtime))
    w = kopia.sprawdz(db, str(bib), str(kop), co_dni=0)
    p = kopia.problemy(db)
    assert w["problemy"] == 1 and p[0]["rodzaj"] == "uszkodzony" and p[0]["z_kopii"]
    assert kopia.przywroc(db, str(bib), str(kop), p[0]["sciezka"])["ok"]
    assert (bib / "b.bin").read_bytes() == b"0123456789" * 100 and not kopia.problemy(db)
    assert (bib / "Odłożone" / "Uszkodzone" / "b.bin").exists()
    # uszkodzona kopia → napraw
    (kop / "a.jpg").write_bytes(b"\0" * os.path.getsize(bib / "a.jpg"))
    kopia.sprawdz(db, str(bib), str(kop), co_dni=0)
    p = kopia.problemy(db)
    assert p and p[0]["rodzaj"] == "kopia"
    assert kopia.napraw_kopie(db, str(bib), str(kop), p[0]["sciezka"])["ok"]
    assert (kop / "a.jpg").read_bytes() == (bib / "a.jpg").read_bytes()
    # zdjęcie, którego nie da się otworzyć
    (bib / "zly.jpg").write_bytes(b"\xff\xd8\xff\xe0 to nie jest zdjecie")
    kopia.sprawdz(db, str(bib), None)
    assert any(x["rodzaj"] == "nie_otwiera" for x in kopia.problemy(db))
    # zmiana EXIF-u przez program (data pliku zostaje) — po „zapomnij” to nie uszkodzenie
    kopia.zapomnij(db, [str(bib / "zly.jpg")])
    assert not any(x["sciezka"].endswith("zly.jpg") for x in kopia.problemy(db))
    db.close()


def test_kopia_jako_zadanie_programu(tmp_path):
    bib, kop = tmp_path / "Bib", tmp_path / "Kopia"
    bib.mkdir()
    (bib / "a.jpg").write_bytes(b"A")
    stan = aplikacja.Stan(tmp_path / "dane")
    stan.ustawienia["cel"] = str(bib)
    assert stan.kopia_ustaw(str(bib / "x"))["blad"]
    i = stan.kopia_ustaw(str(kop), auto=True)
    assert i["folder"] == str(kop) and i["auto"]
    assert stan.kopia_start() is None
    t0 = time.time()
    while stan.zajety() and time.time() - t0 < 20:
        time.sleep(0.05)
    assert (kop / "a.jpg").exists() and stan.kopia_info()["ostatnia"]["skopiowane"] == 1
    assert stan.sprawdzanie_start() is None
    while stan.zajety() and time.time() - t0 < 20:
        time.sleep(0.05)
    i = stan.kopia_info()  # „a.jpg” to nie zdjęcie — zgłoszone jako plik, który się nie otwiera
    assert i["problemy"] == 1 and i["sprawdzanie"]["sprawdzone"] == 1
    assert "problemy: 1" in stan.zad["sprawdzanie"]["komunikat"]


# --- ⇅ kolejność: od najnowszych / od najstarszych -----------------------------------------------------
def test_kolejnosc_od_najnowszych_i_najstarszych(folder):
    tmp, k, ids = folder
    g = galeria.Galeria(tmp / "k.db")
    nazwy = lambda w: [p["nazwa"] for p in w[0]["pliki"]]  # noqa: E731
    assert nazwy(galeria.obsluz_api(g, "/api/g/pliki", {"rok": ["2020"]})) == ["b.jpg", "c.jpg"]  # jak dotąd
    assert nazwy(galeria.obsluz_api(g, "/api/g/pliki", {"rok": ["2020"], "kol": ["nowe"]})) == ["c.jpg", "b.jpg"]
    assert nazwy(galeria.obsluz_api(g, "/api/g/pliki", {"rok": ["2020"], "kol": ["stare"]})) == ["b.jpg", "c.jpg"]
    assert nazwy(galeria.obsluz_api(g, "/api/g/szukaj", {"q": ["2020"], "kol": ["stare"]})) == ["b.jpg", "c.jpg"]
    assert nazwy(galeria.obsluz_api(g, "/api/g/szukaj", {"q": ["2020"]})) == ["c.jpg", "b.jpg"]
    a = g.album_nowy("A", [ids["b.jpg"], ids["c.jpg"]])["id"]
    w = galeria.obsluz_api(g, "/api/g/kolekcja", {"typ": ["album"], "album": [str(a)], "kol": ["nowe"]})
    assert nazwy(w) == ["c.jpg", "b.jpg"]
    galeria.obsluz_api(g, "/api/g/plik", {"id": [str(ids["b.jpg"])], "kol": ["nowe"]})  # nie dotyczy pojedynczego pliku
    assert g._kier() == "ASC"
