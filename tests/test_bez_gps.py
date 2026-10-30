"""📍 Zdjęcia bez GPS: dopasowanie do śladu (Strava / Intervals / GPX), zdjęć z GPS z tej samej chwili, osi czasu Google; GeoCLIP."""
import datetime as dt
import json
import time

import numpy as np
import pytest

from katalogator import bez_gps, galeria, geoclip, podroze, skaner, slady
from test_katalogator import _jpg_z_exif

T = dt.datetime


def _akt(start, pts, id_="1", zrodlo="strava"):
    return {"zrodlo": zrodlo, "id": id_, "nazwa": "Morskie Oko", "typ": "Hike", "start": start,
            "koniec": start + dt.timedelta(seconds=pts[-1][0]), "pts": pts}


def test_dopasowanie_kolejnosc_zrodel():
    slad = _akt(T(2025, 8, 1, 9, 0), [(0, 49.20, 20.00), (3600, 49.30, 20.10)])
    sasiedzi = [(T(2025, 8, 2, 12, 0), 50.0, 19.9), (T(2025, 8, 4, 12, 0), 52.2, 21.0)]
    os_czasu = [{"od": T(2025, 8, 3, 10, 0), "do": T(2025, 8, 3, 12, 0), "typ": "wizyta", "nazwa": "Krupówki", "a": (49.29, 19.95), "b": None},
                {"od": T(2025, 8, 3, 14, 0), "do": T(2025, 8, 3, 16, 0), "typ": "przejazd", "nazwa": "auto", "a": (49.0, 20.0), "b": (50.0, 20.0)}]
    zdj = [{"id": 1, "sciezka": "a", "t": T(2025, 8, 1, 9, 30)},     # w połowie śladu
           {"id": 2, "sciezka": "b", "t": T(2025, 8, 1, 8, 57)},     # 3 min przed startem — początek śladu
           {"id": 3, "sciezka": "c", "t": T(2025, 8, 2, 12, 2)},     # zdjęcie z GPS 2 min wcześniej
           {"id": 4, "sciezka": "d", "t": T(2025, 8, 3, 11, 0)},     # wizyta
           {"id": 5, "sciezka": "e", "t": T(2025, 8, 3, 15, 0)},     # przejazd — w połowie
           {"id": 6, "sciezka": "f", "t": T(2025, 8, 4, 12, 40)},    # sąsiad 40 min — niska pewność
           {"id": 7, "sciezka": "g", "t": T(2025, 9, 1, 12, 0)}]     # nic
    dop, reszta = bez_gps.dopasuj(zdj, [slad], sasiedzi, os_czasu, set())
    d = {z["id"]: z for z in dop}
    assert d[1]["typ"] == "slad" and abs(d[1]["lat"] - 49.25) < 1e-6 and d[1]["pewnosc"] == "wysoka" and "Strava" in d[1]["opis"]
    assert d[2]["typ"] == "slad" and (d[2]["lat"], d[2]["lon"]) == (49.20, 20.00)
    assert d[3]["typ"] == "sasiad" and d[3]["pewnosc"] == "wysoka" and (d[3]["lat"], d[3]["lon"]) == (50.0, 19.9)
    assert d[4]["typ"] == "wizyta" and (d[4]["lat"], d[4]["lon"]) == (49.29, 19.95)
    assert d[5]["typ"] == "przejazd" and abs(d[5]["lat"] - 49.5) < 1e-6 and d[5]["pewnosc"] == "niska"
    assert d[6]["typ"] == "sasiad" and d[6]["pewnosc"] == "niska"
    assert [z["id"] for z in reszta] == [7]
    # odrzucony ślad → następne źródło (tu: żadne, więc reszta)
    dop2, reszta2 = bez_gps.dopasuj(zdj[:1], [slad], sasiedzi, os_czasu, {("a", "slad")})
    assert not dop2 and reszta2[0]["id"] == 1


def test_grupowanie_po_zrodle_i_przerwie():
    z = lambda i, t, k, la=49.0: {"id": i, "sciezka": str(i), "t": t, "klucz": k, "typ": "slad", "lat": la, "lon": 20.0}
    gr = bez_gps.grupuj([z(1, T(2025, 1, 1, 10), "slad:a"), z(2, T(2025, 1, 1, 11), "slad:a"), z(3, T(2025, 1, 1, 15), "slad:a"),
                         z(4, T(2025, 1, 1, 15, 5), "slad:b")])
    assert [[x["id"] for x in g] for g in gr] == [[1, 2], [3], [4]]


def test_gpx_czas_utc_na_lokalny(tmp_path):
    p = tmp_path / "trasa.gpx"
    p.write_text("""<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><name>Sports Tracker: Rysy</name><trkseg>
      <trkpt lat="49.18" lon="20.08"><ele>1400</ele><time>2024-07-10T06:00:00Z</time></trkpt>
      <trkpt lat="49.19" lon="20.09"><time>2024-07-10T07:00:00.500Z</time></trkpt>
      <trkpt lat="49.20" lon="20.10"><time>2024-07-10T08:00:00Z</time></trkpt></trkseg></trk></gpx>""", encoding="utf-8")
    a = bez_gps._gpx_plik(p)[0]
    lok = dt.datetime(2024, 7, 10, 6, 0, tzinfo=dt.timezone.utc).astimezone().replace(tzinfo=None)
    assert a["nazwa"] == "Sports Tracker: Rysy" and a["start"] == lok and a["pts"][-1][0] == 7200
    assert bez_gps._na_sladzie(a, lok + dt.timedelta(hours=1, minutes=30))[0] == pytest.approx(49.195, abs=1e-4)
    (tmp_path / "zly.gpx").write_text("<gpx><trk>", encoding="utf-8")
    assert bez_gps._gpx_plik(tmp_path / "zly.gpx") == []


def test_geoclip_laczenie_skupisk():
    w = bez_gps.polacz_geoclip([[(49.29, 19.95, 0.5), (41.9, 12.5, 0.2)], [(49.30, 19.96, 0.4), (48.85, 2.35, 0.1)]])
    assert w[0][2] == pytest.approx(0.45) and abs(w[0][0] - 49.295) < 0.01 and len(w) == 3


def test_geoclip_przygotowanie_i_galeria(tmp_path):
    p = tmp_path / "x.png"
    from PIL import Image
    Image.new("RGB", (640, 300), (200, 30, 30)).save(p)
    x = geoclip.przygotuj(p)
    assert x.shape == (3, 224, 224) and x.dtype == np.float32 and abs(float(x[0, 0, 0]) - (200 / 255 - 0.48145466) / 0.26862954) < 0.02
    cechy = np.eye(3, 512, dtype=np.float16)
    np.savez_compressed(tmp_path / "g.npz", cechy=cechy, gps=np.array([[10, 20], [30, 40], [50, 60]], np.float32), skala=np.float32(100))
    g = geoclip.Galeria(tmp_path / "g.npz")
    c = np.zeros(512, np.float32)
    c[1] = 1
    naj = g.najlepsze(c, 2)
    assert naj[0][:2] == (30.0, 40.0) and naj[0][2] > 0.99


@pytest.fixture
def biblioteka(tmp_path, monkeypatch):
    k = tmp_path / "zdjecia"
    k.mkdir()
    _jpg_z_exif(k / "z_gps.jpg", data="2025:08:02 12:00:00", gps=(50.0, 19.9))
    _jpg_z_exif(k / "obok.jpg", data="2025:08:02 12:03:00", gps=None)
    _jpg_z_exif(k / "szlak1.jpg", data="2025:08:01 09:30:00", gps=None)
    _jpg_z_exif(k / "szlak2.jpg", data="2025:08:01 09:45:00", gps=None)
    _jpg_z_exif(k / "nic.jpg", data="2020:01:01 12:00:00", gps=None)
    (k / "Dokumenty").mkdir()
    _jpg_z_exif(k / "Dokumenty" / "skan.jpg", data="2025:08:01 09:31:00", gps=None)   # dokumentów nie proponujemy
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    db.close()
    kat = tmp_path / "dane"
    monkeypatch.setattr(bez_gps, "KATALOG", kat)
    monkeypatch.setattr(slady, "aktywnosci_z_czasem", lambda _k: [_akt(T(2025, 8, 1, 9, 0), [(0, 49.20, 20.00), (3600, 49.30, 20.10)])])
    bez_gps._WYNIKI.clear()
    bez_gps._STANY.clear()
    return galeria.Galeria(tmp_path / "k.db", lambda: [str(k)])


def _czekaj(g):
    t0 = time.time()
    while bez_gps.stan(g)["trwa"] and time.time() - t0 < 20:
        time.sleep(0.02)


def test_skan_przeglad_i_decyzje(biblioteka):
    g = biblioteka
    assert galeria.obsluz_api(g, "/api/g/gps", {}, okno=False)[0].get("blad")      # telefon — nie
    assert galeria.obsluz_post(g, "/api/g/gps/skanuj", {})["ok"]
    _czekaj(g)
    s = bez_gps.stan(g)
    assert not s["blad"], s
    assert s["podsumowanie"]["bez_gps"] == 4 and s["podsumowanie"]["propozycje"] == 3 and s["podsumowanie"]["bez_propozycji"] == 1
    r = galeria.obsluz_api(g, "/api/g/gps/grupy", {}, okno=True)[0]
    typy = {x["typ"]: x for x in r["grupy"]}
    assert set(typy) == {"slad", "sasiad"} and typy["slad"]["n"] == 2 and len(typy["slad"]["slad"]) >= 2
    assert typy["sasiad"]["punkty"][0][1:] == [50.0, 19.9]
    # odrzucenie: nie wraca po ponownym skanie
    assert galeria.obsluz_post(g, "/api/g/gps/odrzuc", {"ids": typy["sasiad"]["ids"], "typ": "sasiad"})["odrzucone"] == 1
    assert galeria.obsluz_post(g, "/api/g/gps/skanuj", {})["ok"]
    _czekaj(g)
    r = galeria.obsluz_api(g, "/api/g/gps/grupy", {}, okno=True)[0]
    assert [x["typ"] for x in r["grupy"]] == ["slad"]
    # przyjęcie: zapis zwykłą drogą (/api/g/lokalizacja), potem grupa znika z przeglądu
    x = r["grupy"][0]
    for i, la, lo in x["punkty"]:
        assert galeria.obsluz_post(g, "/api/g/lokalizacja", {"ids": [i], "lat": la, "lon": lo})["zmienione"] == 1
    galeria.obsluz_post(g, "/api/g/gps/przyjete", {"ids": x["ids"]})
    assert galeria.obsluz_api(g, "/api/g/gps/grupy", {}, okno=True)[0]["razem"] == 0
    assert bez_gps.dni_bez_gps(g) == {"2025-08-02", "2020-01-01"}


def test_ustawienia_folder_gpx(biblioteka, tmp_path):
    g = biblioteka
    assert "blad" in galeria.obsluz_post(g, "/api/g/gps/ustawienia", {"folder_gpx": str(tmp_path / "nie-ma")})
    s = galeria.obsluz_post(g, "/api/g/gps/ustawienia", {"folder_gpx": str(tmp_path), "geoclip": True})
    assert s["ustawienia"] == {"folder_gpx": str(tmp_path), "geoclip": True}


def test_slad_z_czasem_w_pamieci(tmp_path, monkeypatch):
    """slady.py zapamiętuje czas punktów (wersja 2) — bez_gps czyta z tego aktywności."""
    pkt = [[49.2 + i * 1e-4, 20.0, 1000.0, i * 10.0, i * 5] for i in range(200)]
    rz = slady.przerzedz(pkt, 10)
    assert rz[0][4] == 0 and rz[-1][4] == 995 and all(b[4] - a[4] >= 10 for a, b in zip(rz[:-2], rz[1:-1]))
    slady._zapisz_slad(tmp_path, "strava", "9", rz)
    slady._zapisz_json(slady.folder_sladow(tmp_path) / "indeks.json",
                       {"strava:9": {"zrodlo": "strava", "id": "9", "start": "2025-08-01T09:00:00", "nazwa": "x", "typ": "Hike", "km": 1,
                                     "slad": True, "wersja": slady.WERSJA_PAMIECI},
                        "strava:8": {"zrodlo": "strava", "id": "8", "start": "2025-08-01T09:00:00", "nazwa": "stary", "typ": "Hike", "km": 1, "slad": True}})
    a = slady.aktywnosci_z_czasem(tmp_path)
    assert len(a) == 1 and a[0]["koniec"] == T(2025, 8, 1, 9, 16, 35) and a[0]["pts"][1][0] == 10


def test_gpx_przerzedzenie_i_pamiec_na_dysku(tmp_path, monkeypatch):
    monkeypatch.setattr(bez_gps, "KATALOG", tmp_path / "dane")
    p = tmp_path / "st.gpx"
    pkt = "".join(f'<trkpt lat="{49 + i * 1e-4}" lon="20"><time>2024-07-10T06:{i // 60:02d}:{i % 60:02d}Z</time></trkpt>' for i in range(121))
    p.write_text(f'<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>{pkt}</trkseg></trk></gpx>', encoding="utf-8")
    a = bez_gps._gpx_plik(p)[0]
    assert [x[0] for x in a["pts"]] == [i * 10.0 for i in range(13)]       # punkt co 10 s
    bez_gps._GPX.clear()
    p.write_bytes(p.read_bytes())   # ta sama treść, inny czas zmiany pliku — czytamy na nowo
    import os
    os.utime(p, (1_700_000_000, 1_700_000_000))
    b = bez_gps._gpx_plik(p)[0]
    bez_gps._GPX.clear()
    c = bez_gps._gpx_plik(p)[0]                                              # z pamięci na dysku
    assert c["pts"] == b["pts"] and c["start"] == b["start"] and len(list((tmp_path / "dane" / "gpx-pamiec").glob("*.json"))) == 1
