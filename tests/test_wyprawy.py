"""✈ Generator wypraw z osi czasu Google — dane wymyślone (żadnych danych osobistych)."""
import json
from datetime import datetime, timedelta, timezone

from katalogator import podroze, wyprawy

DOM = (52.2297, 21.0122)   # Warszawa


def _wizyta(t0, godz, c, typ=None):
    t1 = t0 + timedelta(hours=godz)
    return {"startTime": t0.isoformat(), "endTime": t1.isoformat(),
            "visit": {"topCandidate": {"placeLocation": {"latLng": f"{c[0]}°, {c[1]}°"}, **({"semanticType": typ} if typ else {})}}}


def _ruch(t0, godz, a, b, typ, m):
    return {"startTime": t0.isoformat(), "endTime": (t0 + timedelta(hours=godz)).isoformat(),
            "activity": {"start": {"latLng": f"{a[0]}°, {a[1]}°"}, "end": {"latLng": f"{b[0]}°, {b[1]}°"},
                         "distanceMeters": m, "topCandidate": {"type": typ}},
            "timelinePath": [{"point": f"{a[0]}°, {a[1]}°"}, {"point": f"{b[0]}°, {b[1]}°"}]}


def _os_czasu():
    t = datetime(2025, 8, 1, 8, tzinfo=timezone.utc)
    zak, rzym = (49.2992, 19.9496), (41.9028, 12.4964)
    seg = [_wizyta(t - timedelta(days=d), 10, DOM, "HOME") for d in range(1, 6)]
    seg += [_ruch(t, 4, DOM, zak, "IN_PASSENGER_VEHICLE", 300000)]
    seg += [_wizyta(t + timedelta(hours=5 + 6 * i), 4, (zak[0] + i * 0.01, zak[1]), None) for i in range(6)]
    seg += [_ruch(t + timedelta(days=2), 2, zak, (49.25, 19.98), "WALKING", 8000)]
    t2 = datetime(2025, 10, 10, 6, tzinfo=timezone.utc)
    seg += [_ruch(t2, 2, DOM, rzym, "FLYING", 1300000), _wizyta(t2 + timedelta(hours=3), 8, rzym)]
    seg += [_wizyta(t2 + timedelta(days=1), 8, (rzym[0] + 0.01, rzym[1] + 0.01))]
    seg += [_wizyta(datetime(2025, 6, 1, 8, tzinfo=timezone.utc), 5, (52.4, 16.9))]   # Poznań ~280 km, ale 1 wpis — to nie wyprawa
    return {"semanticSegments": seg}


def test_dom_wyprawy_nazwy_i_dni(tmp_path):
    p = tmp_path / "Timeline.json"
    p.write_text(json.dumps(_os_czasu()), encoding="utf-8")
    zd = wyprawy.zdarzenia(wyprawy.wczytaj(str(p)))
    dom = wyprawy.wykryj_dom(zd)
    assert wyprawy.odl_km(dom, DOM) < 1
    w = wyprawy.zbuduj(wyprawy.wyprawy_z_zdarzen(zd, dom), dom, {})
    assert [x["startDate"] for x in w] == ["2025-10-10", "2025-08-01"]               # najnowsza pierwsza, Poznań pominięty
    rzym, tatry = w
    assert rzym["icon"] == "🇮🇹" and "Włochy" in rzym["destination"] and rzym["title"].endswith("(Październik 2025)")
    assert rzym["totalKmFlight"] == 1300 and rzym["durationDays"] == 2
    assert "Zakopane" in tatry["destination"] and tatry["title"].endswith("(Sierpień 2025)")
    assert tatry["totalKmWalk"] == 8.0 and tatry["totalKmDrive"] == 300.0
    assert tatry["days"][0]["dayNumber"] == 1 and tatry["days"][0]["path"] and tatry["days"][0]["events"]
    assert all(set(d) >= {"date", "events", "path", "mountainTracks"} for d in tatry["days"])


def test_zapis_zachowuje_dopiski_i_robi_kopie(tmp_path):
    p = tmp_path / "Timeline.json"
    p.write_text(json.dumps(_os_czasu()), encoding="utf-8")
    d = podroze.folder_danych(tmp_path / "dane")
    d.mkdir(parents=True)
    (d / "sample-trips.json").write_text(json.dumps({"trips": [{"startDate": "2025-08-01", "photos": [{"id": "x"}],
                                                                "bookings": ["rezerwacja"], "title": "stary"}]}), encoding="utf-8")
    wyn = wyprawy.generuj(tmp_path / "dane", str(p))
    assert wyn["wyprawy"] == 2
    dane = json.loads((d / "sample-trips.json").read_text(encoding="utf-8"))
    tatry = next(t for t in dane["trips"] if t["startDate"] == "2025-08-01")
    assert tatry["photos"] == [{"id": "x"}] and tatry["bookings"] == ["rezerwacja"] and tatry["title"] != "stary"
    assert (d / "sample-trips.json.poprzedni").is_file()


def test_zly_plik_i_formaty_wspolrzednych(tmp_path):
    import pytest
    (tmp_path / "x.json").write_text('{"cos": 1}', encoding="utf-8")
    with pytest.raises(ValueError, match="semanticSegments"):
        wyprawy.wczytaj(str(tmp_path / "x.json"))
    assert wyprawy.wsp("geo:50.5,19.5") == (50.5, 19.5) and wyprawy.wsp({"latitudeE7": 505000000, "longitudeE7": 195000000}) == (50.5, 19.5)
    assert wyprawy.wsp("200°, 10°") is None and wyprawy.wsp(None) is None


def test_opis_osm():
    w = wyprawy.opisz_osm({"type": "hotel", "name": "Hotel Tatry", "address": {"town": "Zakopane", "country": "Polska"}})
    assert w == {"name": "Hotel Tatry (Zakopane)", "city": "Zakopane", "country": "Polska", "category": "lodging", "icon": "🏨"}


def test_generowanie_przez_api(tmp_path):
    import threading
    import time
    import urllib.request
    from katalogator import aktualizacje, aplikacja
    p = tmp_path / "Timeline.json"
    p.write_text(json.dumps(_os_czasu()), encoding="utf-8")
    (tmp_path / "dane").mkdir()
    aktualizacje.zapisz_ustawienia(tmp_path / "dane", powitanie_widziane=True)
    serwer, url, stan = aplikacja.uruchom_serwer(tmp_path / "dane")
    threading.Thread(target=serwer.serve_forever, daemon=True).start()
    try:
        w = stan.podroze_akcja({"akcja": "generuj", "plik": str(tmp_path / "brak.json")})
        assert "Nie ma takiego pliku" in w["blad"]
        assert stan.podroze_akcja({"akcja": "generuj", "plik": str(p)})["ma_dane"] in (True, False)
        for _ in range(100):
            if not stan.podroze_info()["import"]["trwa"]:
                break
            time.sleep(0.05)
        info = stan.podroze_info()
        assert info["ma_dane"] and info["wyprawy"] == 2 and "Gotowe" in info["import"]["komunikat"], info["import"]
    finally:
        serwer.shutdown()
