import json
import threading
import urllib.error
from urllib.parse import unquote

import pytest

from katalogator import __version__, aktualizacje, logi
from test_aplikacja import app  # noqa: F401


def test_logi_i_nieobsluzony_blad_w_watku(tmp_path):
    plik = logi.konfiguruj(tmp_path)
    logi.LOG.info("start testu")

    def zly():
        raise RuntimeError("awaria w wątku")
    t = threading.Thread(target=zly, name="Robotnik")
    t.start(); t.join()
    tekst = logi.ogon(50)
    assert "start testu" in tekst and "awaria w wątku" in tekst and "Robotnik" in tekst
    assert plik.exists()


def _info(tag, zasoby=("Katalogator-Setup-9.9.9.exe",)):
    return lambda: {"tag_name": tag, "html_url": "https://github.com/x/y/releases/tag/" + tag, "body": "Nowości",
                    "assets": [{"name": n, "browser_download_url": "https://github.com/x/y/releases/download/" + n}
                               for n in zasoby]}


def test_aktualizacje(tmp_path):
    w = aktualizacje.sprawdz(tmp_path, pobierz=_info("v9.9.9"))
    assert w["nowa"] and w["najnowsza"] == "9.9.9" and w["url_instalatora"].endswith("Setup-9.9.9.exe")
    # pamięć podręczna: drugi raz nie pyta GitHuba
    w2 = aktualizacje.sprawdz(tmp_path, pobierz=lambda: (_ for _ in ()).throw(AssertionError("nie powinno pytać")))
    assert w2["nowa"]
    assert not aktualizacje.sprawdz(tmp_path, wymus=True, pobierz=_info("v" + __version__))["nowa"]
    assert not aktualizacje.sprawdz(tmp_path, wymus=True, pobierz=_info("v0.1.0"))["nowa"]

    def brak():
        raise urllib.error.URLError("brak sieci")
    assert aktualizacje.sprawdz(tmp_path, wymus=True, pobierz=brak)["blad"]
    aktualizacje.zapisz_ustawienia(tmp_path, sprawdzaj_aktualizacje=False)
    w3 = aktualizacje.sprawdz(tmp_path, pobierz=_info("v9.9.9"))
    assert not w3["wlaczone"] and w3["najnowsza"] is None
    assert aktualizacje.wersja_krotka("v1.10.0") > aktualizacje.wersja_krotka("1.9.9")
    with pytest.raises(ValueError):
        aktualizacje.pobierz_i_uruchom("https://zly.example.com/x.exe")


def test_raport_i_zgloszenie(app, tmp_path, monkeypatch):  # noqa: F811
    api, _, stan = app
    logi.konfiguruj(stan.katalog)
    logi.LOG.error("Testowy błąd XYZ")
    r = json.loads(api("/api/raport-bledow")[1])
    assert "=== Raport Katalogatora ===" in r["tekst"] and "Testowy błąd XYZ" in r["tekst"]
    assert f"Wersja: {__version__}" in r["tekst"]
    api("/api/log", {"tekst": "TypeError: x is undefined (plan.js:10)"})
    assert "plan.js:10" in logi.ogon(20)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / "Downloads").mkdir()
    plik = json.loads(api("/api/raport-bledow/zapisz", {})[1])["plik"]
    assert plik.startswith(str(tmp_path / "Downloads")) and "Testowy błąd XYZ" in open(plik, encoding="utf-8").read()
    otwarte = []
    monkeypatch.setattr("webbrowser.open", lambda u: otwarte.append(u))
    url = json.loads(api("/api/raport-bledow/github", {"opis": "Nie działa skan\nszczegóły"})[1])["url"]
    assert url.startswith("https://github.com/mbarczykmb-afk/chmura/issues/new?title=") and otwarte == [url]
    assert "Nie działa skan" in unquote(url) and "Testowy błąd XYZ" in unquote(url) and len(url) <= 7800
    o = json.loads(api("/api/o-programie")[1])
    assert o["wersja"] == __version__ and o["plik_logu"].endswith("katalogator.log")


def test_blad_obslugi_zwraca_komunikat(app, monkeypatch):  # noqa: F811
    api, _, stan = app
    logi.konfiguruj(stan.katalog)
    monkeypatch.setattr(stan, "raport_diagnostyczny", lambda: 1 / 0)
    with pytest.raises(urllib.error.HTTPError) as e:
        api("/api/raport-bledow")
    assert e.value.code == 500 and "ZeroDivisionError" in json.loads(e.value.read())["blad"]
    assert "ZeroDivisionError" in logi.ogon(30)


def test_baza_nie_blokuje_sie_przy_dlugim_zapisie(tmp_path):
    """Zadanie w tle trzyma transakcję — okno musi móc czytać od razu, a zapis ma poczekać, nie zgłaszać błędu."""
    import time
    from katalogator import skaner
    baza = tmp_path / "k.db"
    skaner.otworz_baze(baza).close()
    otwarta, koniec = threading.Event(), threading.Event()

    def zadanie():
        db = skaner.otworz_baze(baza)
        db.execute("INSERT INTO skany(korzen, start) VALUES ('x', 1)")  # transakcja otwarta
        otwarta.set()
        time.sleep(1.5)
        db.commit()
        db.close()
        koniec.set()

    threading.Thread(target=zadanie).start()
    otwarta.wait(5)
    okno = skaner.otworz_baze(baza)
    t0 = time.time()
    assert okno.execute("SELECT COUNT(*) FROM pliki").fetchone()[0] == 0  # odczyt bez czekania (WAL)
    assert time.time() - t0 < 1
    okno.execute("INSERT INTO skany(korzen, start) VALUES ('y', 2)")  # czeka na zadanie, bez błędu
    okno.commit()
    assert koniec.wait(5)
    assert okno.execute("SELECT COUNT(*) FROM skany").fetchone()[0] == 2


def test_zablokowany_instalator_czytelny_komunikat(tmp_path):
    wywolania = []

    def popen(args, **kw):
        wywolania.append(args)
        if args[0] != "explorer":
            e = OSError("Zasady kontroli aplikacji zablokowały ten plik")
            e.winerror = 4551
            raise e
    plik = tmp_path / "Katalogator-Setup-9.9.9.exe"
    with pytest.raises(OSError, match="Inteligentna kontrola aplikacji") as e:
        aktualizacje.uruchom_instalator(plik, popen=popen)
    assert str(plik) in str(e.value)
    assert wywolania[-1] == ["explorer", "/select,", str(plik)]  # od razu widać pobrany plik


def test_inny_blad_instalatora_bez_zmian(tmp_path):
    def popen(args, **kw):
        raise FileNotFoundError(2, "brak pliku")
    with pytest.raises(FileNotFoundError):
        aktualizacje.uruchom_instalator(tmp_path / "x.exe", popen=popen)
