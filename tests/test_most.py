"""🌍 Most do domu: przez Tailscale Funnel tylko klucz (nie PIN), tylko oglądanie; klucz zapamiętany."""

import json
import urllib.error
import urllib.request

import pytest

from katalogator import aplikacja, galeria, most, pilot
from test_katalogator import _jpg_z_exif

MOST = {"Host": "dom.tail1234.ts.net", "X-Forwarded-For": "203.0.113.7"}


def _serwer(stan):
    return galeria.SerwerGalerii(stan.galeria("wszystko"), port=0, pin="1357", host="127.0.0.1",
                                 pilot=pilot.Pilot(stan, True), galerie=stan.galeria).start()


def _zapytaj(s, sciezka, dane=None, token=None, naglowki=None):
    r = urllib.request.Request(f"http://127.0.0.1:{s.port}{sciezka}", data=None if dane is None else json.dumps(dane).encode(),
                               headers={"Content-Type": "application/json", **(naglowki or {}),
                                        **({"X-Token": token} if token else {})})
    with urllib.request.urlopen(r, timeout=10) as o:
        t = o.read()
        return json.loads(t) if o.headers.get("Content-Type", "").startswith("application/json") else t


def _kod(f, *a, **k):
    with pytest.raises(urllib.error.HTTPError) as e:
        f(*a, **k)
    return e.value.code


def test_klucz_mostu():
    k = most.nowy_klucz()
    assert len(k) == 23 and k.count("-") == 3 and not set(k.replace("-", "")) - set(most._ALFABET)
    assert most.normalizuj_klucz(" K7PQ2-9hm4x ") == "k7pq29hm4x"


def test_most_tylko_klucz_i_tylko_ogladanie(tmp_path):
    zr = tmp_path / "zdjecia"
    zr.mkdir()
    _jpg_z_exif(zr / "a.jpg", data="2021:05:01 10:00:00", gps=None)
    stan = aplikacja.Stan(tmp_path / "dane")
    stan.ustawienia["zrodla"] = [{"sciezka": str(zr), "tryb": "kopiuj"}]
    s = _serwer(stan)
    try:
        # most wyłączony: z internetu nic
        assert _kod(_zapytaj, s, "/api/g/zaloguj", {"pin": "1357"}, naglowki=MOST) == 403
        stan.serwer_tel = s
        stan._most_na_serwerze(s, True)
        klucz = stan._most_klucz()
        # PIN telefonu przez most nie działa, klucz — tak (z myślnikami albo bez, wielkość liter bez znaczenia)
        assert _kod(_zapytaj, s, "/api/g/zaloguj", {"pin": "1357"}, naglowki=MOST) == 401
        t = _zapytaj(s, "/api/g/zaloguj", {"pin": klucz.upper().replace("-", "")}, naglowki=MOST)["t"]
        assert t == s.staly_most
        # token z domowego PIN-u nie otwiera mostu, a token mostu — sieci domowej
        t_dom = _zapytaj(s, "/api/g/zaloguj", {"pin": "1357"})["t"]
        assert _kod(_zapytaj, s, "/api/g/lata", token=t_dom, naglowki=MOST) == 401
        assert _kod(_zapytaj, s, "/api/g/lata", token=t) == 401
        # przez most: Przeglądarka tak, pilot / pełny program / zmiany — nie
        assert _zapytaj(s, "/api/g/lata", token=t, naglowki=MOST)["razem"] >= 0
        assert b"galeria.js" in _zapytaj(s, "/", naglowki=MOST)  # od razu Przeglądarka, bez pilota
        assert _kod(_zapytaj, s, "/api/pilot", token=t, naglowki=MOST) == 403
        assert _kod(_zapytaj, s, "/api/pilot/skan", {}, token=t, naglowki=MOST) == 403
        assert _kod(_zapytaj, s, "/program", token=t, naglowki=MOST) == 403
        assert _kod(_zapytaj, s, "/api/g/usun", {"ids": [1]}, token=t, naglowki=MOST) == 403
        # pośrednik na tym komputerze (Funnel) bez nazwy *.ts.net też liczy się jako most
        assert _kod(_zapytaj, s, "/api/g/lata", token=t_dom, naglowki={"X-Forwarded-For": "203.0.113.7"}) == 401
        # w domu po staremu: PIN i pilot działają
        assert _zapytaj(s, "/api/pilot", token=t_dom)["kroki"]
        # nowy klucz — stary token mostu przestaje działać
        stan._most_klucz(nowy=True)
        stan._most_na_serwerze(s, True)
        assert _kod(_zapytaj, s, "/api/g/lata", token=t, naglowki=MOST) == 401
        # wyłączenie
        stan._most_na_serwerze(s, False)
        assert _kod(_zapytaj, s, "/api/g/lata", token=s.staly_most or "x", naglowki=MOST) == 403
    finally:
        s.stop()


def test_most_bez_tailscale(tmp_path, monkeypatch):
    monkeypatch.setattr(most, "tailscale", lambda: None)
    stan = aplikacja.Stan(tmp_path / "dane")
    w = stan.most(True)
    assert "blad" in w and "Tailscale" in w["blad"]
    assert not stan.most_info()["wlaczony"] and stan.serwer_tel is None  # serwer telefonu nie włączył się „przy okazji”


def test_most_wlaczenie_przez_funnel(tmp_path, monkeypatch):
    wywolania = []
    monkeypatch.setattr(most, "tailscale", lambda: "/bin/tailscale")
    monkeypatch.setattr(most, "stan", lambda: {"tailscale": True, "zalogowany": True, "dns": "dom.tail1.ts.net",
                                               "adres": "https://dom.tail1.ts.net/"})

    def udawane(argumenty, czas=25):
        wywolania.append(argumenty)
        return 0, ""
    monkeypatch.setattr(most, "_uruchom", udawane)
    stan = aplikacja.Stan(tmp_path / "dane")
    try:
        w = stan.most(True)
        assert w["wlaczony"] and w["adres"] == "https://dom.tail1.ts.net/" and w["link"].endswith("#k=" + w["klucz"])
        assert wywolania[-1] == ["funnel", "--bg", str(stan.serwer_tel.port)]
        assert stan.serwer_tel.klucz_mostu == w["klucz"]
        w2 = stan.most(False)
        assert not w2["wlaczony"] and wywolania[-1][0] == "funnel" and stan.serwer_tel.klucz_mostu is None
    finally:
        if stan.serwer_tel:
            stan.serwer_tel.stop()


def test_funnel_prosi_o_zgode(monkeypatch):
    monkeypatch.setattr(most, "tailscale", lambda: "/bin/tailscale")
    monkeypatch.setattr(most, "stan", lambda: {"tailscale": True, "zalogowany": True, "dns": "d.ts.net", "adres": "https://d.ts.net/"})
    monkeypatch.setattr(most, "_uruchom", lambda a, czas=25: (-1, "Funnel is not enabled on your tailnet.\nTo enable, visit:\n\n"
                                                                     "         https://login.tailscale.com/f/funnel?node=abc123\n"))
    w = most.wlacz(8765)
    assert w["link"] == "https://login.tailscale.com/f/funnel?node=abc123" and "zgod" in w["blad"]
