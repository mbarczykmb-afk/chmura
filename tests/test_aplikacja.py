import json
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse, parse_qs

import pytest

from katalogator import aplikacja
from test_katalogator import _drzewo


@pytest.fixture
def app(tmp_path):
    serwer, url, stan = aplikacja.uruchom_serwer(tmp_path / "dane")
    (tmp_path / "dane").mkdir(exist_ok=True)
    t = threading.Thread(target=serwer.serve_forever, daemon=True)
    t.start()
    u = urlparse(url)
    baza = f"{u.scheme}://{u.netloc}"
    token = parse_qs(u.query)["t"][0]

    def api(sciezka, dane=None, tok=token):
        req = urllib.request.Request(baza + sciezka, headers={"X-Token": tok})
        if dane is not None:
            req.data = json.dumps(dane).encode()
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode()

    yield api, url, stan
    serwer.shutdown()
    serwer.server_close()


def test_strona_wymaga_tokenu(app):
    api, url, _ = app
    with urllib.request.urlopen(url, timeout=5) as r:
        assert "Katalogator" in r.read().decode()
    with pytest.raises(urllib.error.HTTPError) as e:
        api("/api/stan", tok="zly")
    assert e.value.code == 403
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(url.split("?")[0], timeout=5)


def test_ustawienia_skan_raport(app, tmp_path):
    api, _, stan = app
    k = _drzewo(tmp_path)
    cel = tmp_path / "cel"
    (cel / "Zdjęcia").mkdir(parents=True)
    (cel / "Zdjęcia" / "stare.txt").write_text("x")

    _, body = api("/api/ustawienia", {"zrodla": [str(k), str(k), " "], "cel": str(cel)})
    s = json.loads(body)
    assert s["zrodla"] == [{"sciezka": str(k), "tryb": "kopiuj"}] and s["cel"] == str(cel) and not s["ma_wyniki"]
    assert json.loads(stan.plik_ustawien.read_text(encoding="utf-8"))["cel"] == str(cel)

    api("/api/skanuj", {})
    for _ in range(100):
        s = json.loads(api("/api/stan")[1])
        if not s["skan"]["trwa"]:
            break
        time.sleep(0.05)
    assert s["skan"]["blad"] == "" and s["ma_wyniki"]
    assert s["skan"]["przejrzano"] == 7  # 6 w źródle + 1 w miejscu docelowym
    _, html = api("/raport")
    assert "Raport ze skanowania" in html and "Praca" in html


def test_skan_bez_folderu_i_zly_folder(app, tmp_path):
    api, _, _ = app
    with pytest.raises(urllib.error.HTTPError) as e:
        api("/api/skanuj", {})
    assert e.value.code == 400
    api("/api/ustawienia", {"zrodla": [str(tmp_path / "nie_ma")]})
    with pytest.raises(urllib.error.HTTPError) as e:
        api("/api/skanuj", {})
    assert "Nie mogę otworzyć" in json.loads(e.value.read())["blad"]


def test_przerwanie(tmp_path):
    from katalogator import skaner
    k = _drzewo(tmp_path)
    db = skaner.otworz_baze(tmp_path / "k.db")
    ev = threading.Event(); ev.set()
    with pytest.raises(skaner.Przerwano):
        skaner.skanuj(str(k), db, postep=lambda *a: None, przerwij=ev)
