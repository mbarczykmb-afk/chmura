"""✈ Podróże jako część Katalogatora: import danych, dostęp do zdjęć tylko z biblioteki, trasy /podroze/ i ich uwierzytelnianie."""
import http.client
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from PIL import Image

from katalogator import aplikacja, galeria, pilot, podroze

TRIPS = {"trips": [{"id": "t1", "title": "Tatry", "startDate": "2025-08-01", "endDate": "2025-08-03", "days": []},
                   {"id": "t2", "title": "Madera", "startDate": "2025-12-14", "endDate": "2025-12-20", "days": []}],
         "totalTrips": 2}


def _jpg(sciezka, kolor="red"):
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 24), kolor).save(sciezka)
    return sciezka


@pytest.fixture
def projekt(tmp_path):
    """Dotychczasowy folder projektu Timeline Travels (z danymi)."""
    k = tmp_path / "google-timeline-travels"
    k.mkdir()
    (k / "sample-trips.json").write_text(json.dumps(TRIPS), encoding="utf-8")
    (k / "matched_user_photos.json").write_text("[]", encoding="utf-8")
    (k / "tajne.json").write_text("{}", encoding="utf-8")  # spoza listy — nie kopiujemy
    _jpg(k / "thumbnails" / "mini1.jpg")
    (k / "thumbnails" / "notatki.txt").write_text("x", encoding="utf-8")
    return k


def _czekaj_import(timeout=15):
    t0 = time.time()
    while podroze._import["trwa"] and time.time() - t0 < timeout:
        time.sleep(0.02)
    assert not podroze._import["trwa"]


def test_import_kopiuje_tylko_dozwolone_pliki(tmp_path, projekt):
    dane = tmp_path / "dane"
    assert "Nie ma takiego folderu" in podroze.importuj(dane, str(tmp_path / "brak"))["blad"]
    assert "sample-trips.json" in podroze.importuj(dane, str(tmp_path))["blad"]
    assert not podroze.stan(dane, {}, [])["ma_dane"]
    assert podroze.importuj(dane, str(projekt)) == {"ok": True}
    _czekaj_import()
    s = podroze.stan(dane, {}, [])
    assert s["ma_dane"] and s["wyprawy"] == 2 and not s["import"]["blad"]
    d = podroze.folder_danych(dane)
    assert sorted(p.name for p in d.iterdir()) == ["matched_user_photos.json", "sample-trips.json", "thumbnails"]
    assert [p.name for p in (d / "thumbnails").iterdir()] == ["mini1.jpg"]       # tylko zdjęcia, bez notatek
    assert (projekt / "sample-trips.json").is_file()                               # oryginał zostaje
    w = podroze.wersja(dane)
    assert w["totalTrips"] == 2 and w["version"] > 0
    assert podroze.usun_dane(dane) == {"ok": True} and not podroze.stan(dane, {}, [])["ma_dane"]
    assert podroze.wersja(dane)["totalTrips"] == 0 and (projekt / "sample-trips.json").is_file()


def test_pliki_danych_tylko_z_listy(tmp_path, projekt):
    dane = tmp_path / "dane"
    podroze.importuj(dane, str(projekt))
    _czekaj_import()
    assert podroze.plik_danych(dane, "sample-trips.json").name == "sample-trips.json"
    assert podroze.plik_danych(dane, "thumbnails/mini1.jpg")
    for zle in ("../sample-trips.json", "thumbnails/../sample-trips.json", "thumbnails/a/b.jpg", "tajne.json",
                "thumbnails/notatki.txt", "thumbnails\\mini1.jpg", "places_cache.json", ""):
        assert podroze.plik_danych(dane, zle) is None, zle


def test_zdjecia_tylko_z_folderow_biblioteki(tmp_path):
    dane = tmp_path / "dane"
    biblioteka = tmp_path / "Uporządkowane"
    foto = _jpg(biblioteka / "Zdjęcia" / "Zdjęcia z 2025" / "Madera" / "20251214_100000.jpg")
    na_zewnatrz = _jpg(tmp_path / "prywatne" / "skan.jpg")
    korz = [str(biblioteka)]
    assert podroze.rozwiaz_zdjecie(str(foto), korz, dane) == (foto.resolve(), "ok")
    assert podroze.rozwiaz_zdjecie(str(na_zewnatrz), korz, dane) == (None, "zabronione")
    assert podroze.rozwiaz_zdjecie(str(biblioteka / ".." / "prywatne" / "skan.jpg"), korz, dane) == (None, "zabronione")
    assert podroze.rozwiaz_zdjecie(str(biblioteka / "brak.jpg"), korz, dane) == (None, "brak")
    assert podroze.rozwiaz_zdjecie(str(foto), [], dane) == (None, "zabronione")                        # brak folderów = nic
    for zle in ("/etc/passwd", str(biblioteka / "dane.json"), str(biblioteka / "x.svg"), "", "a\x00.jpg"):
        assert podroze.rozwiaz_zdjecie(zle, korz, dane)[0] is None
    # dowiązanie wychodzące poza bibliotekę nie omija ograniczenia
    if hasattr(os, "symlink"):
        try:
            os.symlink(tmp_path / "prywatne", biblioteka / "skrot")
        except OSError:
            pass
        else:
            assert podroze.rozwiaz_zdjecie(str(biblioteka / "skrot" / "skan.jpg"), korz, dane) == (None, "zabronione")
    # sama nazwa: miniatura podróży, potem baza Przeglądarki (ale tylko, jeśli plik leży w bibliotece)
    podroze.folder_danych(dane).joinpath("thumbnails").mkdir(parents=True)
    mini = _jpg(podroze.folder_danych(dane) / "thumbnails" / "mini.jpg")
    assert podroze.rozwiaz_zdjecie("mini.jpg", korz, dane) == (mini, "ok")
    assert podroze.rozwiaz_zdjecie("20251214_100000.jpg", korz, dane, lambda n: str(foto)) == (foto, "ok")
    assert podroze.rozwiaz_zdjecie("skan.jpg", korz, dane, lambda n: str(na_zewnatrz)) == (None, "brak")
    assert podroze.rozwiaz_zdjecie("x.jpg", korz, dane, lambda n: 1 / 0) == (None, "brak")


# ── trasy HTTP w programie ──────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def program(tmp_path, projekt):
    biblioteka = tmp_path / "Uporządkowane"
    foto = _jpg(biblioteka / "Madera" / "20251214_100000.jpg", "blue")
    obca = _jpg(tmp_path / "prywatne" / "skan.jpg")
    serwer, url, stan = aplikacja.uruchom_serwer(tmp_path / "dane")
    threading.Thread(target=serwer.serve_forever, daemon=True).start()
    stan.podroze_akcja({"korzenie": [str(biblioteka)]})
    stan.podroze_akcja({"akcja": "importuj", "folder_importu": str(projekt)})
    _czekaj_import()
    host, port = url.split("//")[1].split("/")[0].split(":")
    token = url.split("?t=")[1]

    def get(sciezka, cookie=None, metoda="GET", dane=None, naglowki=None):
        c = http.client.HTTPConnection(host, int(port), timeout=10)
        h = dict(naglowki or {})
        if cookie:
            h["Cookie"] = cookie
        c.request(metoda, sciezka, body=dane, headers=h)
        r = c.getresponse()
        return r.status, r.read(), dict(r.getheaders())
    yield {"get": get, "token": token, "foto": foto, "obca": obca, "stan": stan, "url": url}
    serwer.shutdown()


def test_strona_wymaga_tokenu_i_ustawia_ciasteczko(program):
    g, t = program["get"], program["token"]
    assert g("/podroze/")[0] == 403
    assert g("/podroze/?t=zly")[0] == 403
    kod, tresc, nag = g(f"/podroze/?t={t}")
    assert kod == 200 and b'<base href="/podroze/">' in tresc and b"cdn.tailwindcss" not in tresc and b"unpkg.com" not in tresc
    ciastko = nag["Set-Cookie"]
    assert ciastko.startswith(f"kat_podroze={t}") and "HttpOnly" in ciastko and "SameSite=Strict" in ciastko and "Path=/podroze" in ciastko
    assert g("/podroze", metoda="GET")[0] == 302                                   # ukośnik na końcu (adresy względne)
    assert g("/podroze/?t=" + t, naglowki={})[0] == 200


def test_zasoby_i_dane_przez_ciasteczko(program):
    g, t = program["get"], program["token"]
    c = f"kat_podroze={t}"
    assert g("/podroze/api/version")[0] == 403 and g("/podroze/api/version", cookie="kat_podroze=zle")[0] == 403
    kod, tresc, _ = g("/podroze/api/version", c)
    assert kod == 200 and json.loads(tresc)["totalTrips"] == 2
    for plik, typ in (("app.js", "javascript"), ("podroze.css", "text/css"), ("jszip.min.js", "javascript"),
                      ("motyw.css", "text/css"), ("katalogator-motyw.js", "javascript")):
        kod, tresc, nag = g("/podroze/" + plik, c)
        assert kod == 200 and typ in nag["Content-Type"] and len(tresc) > 100, plik
    kod, tresc, nag = g("/podroze/sample-trips.json", c)
    assert kod == 200 and json.loads(tresc)["trips"][1]["title"] == "Madera" and int(nag["Content-Length"]) == len(tresc)
    assert g("/podroze/thumbnails/mini1.jpg", c)[0] == 200
    assert g("/podroze/tajne.json", c)[0] == 404 and g("/podroze/places_cache.json", c)[0] == 404   # brak pliku
    assert g("/podroze/../aplikacja.py", c)[0] == 404 and g("/podroze/%2e%2e/aplikacja.py", c)[0] == 404
    assert g("/podroze/api/user-photos", c)[0] == 200
    kod, tresc, _ = g("/podroze/sample-trips.json", c, naglowki={"Range": "bytes=0-9"})
    assert kod == 206 and len(tresc) == 10


def test_zdjecia_przez_serwer_tylko_z_biblioteki(program):
    from urllib.parse import quote
    g, t = program["get"], program["token"]
    c = f"kat_podroze={t}"
    kod, tresc, nag = g("/podroze/api/photo?path=" + quote(str(program["foto"])), c)
    assert kod == 200 and nag["Content-Type"] == "image/jpeg" and tresc[:2] == b"\xff\xd8" and "max-age" in nag["Cache-Control"]
    assert g("/podroze/api/photo?path=" + quote(str(program["obca"])), c)[0] == 403         # spoza biblioteki
    assert g("/podroze/api/photo?path=" + quote("/etc/passwd"), c)[0] == 403
    kod, tresc, nag = g("/podroze/api/photo?path=" + quote(str(program["foto"].parent / "brak.jpg")), c)
    assert kod == 200 and nag["Content-Type"].startswith("image/svg+xml") and b"brak.jpg" in tresc   # zamiast zepsutego obrazka
    kod, tresc, _ = g("/podroze/api/photo?path=" + quote(program["foto"].name), c)                   # sama nazwa: nie ma w bazie
    assert kod == 200 and tresc.startswith(b"<svg")


def test_post_i_panel_wymagaja_dostepu(program):
    g, t = program["get"], program["token"]
    assert g("/podroze/api/reindex", metoda="POST", dane=b"{}")[0] == 403
    assert g("/podroze/api/reindex", f"kat_podroze={t}", "POST", b"{}")[0] == 200
    assert g("/api/podroze")[0] == 403                                                  # panel: zwykły token programu
    kod, tresc, _ = g(f"/api/podroze?t={t}")
    s = json.loads(tresc)
    assert kod == 200 and s["ma_dane"] and s["wyprawy"] == 2 and len(s["korzenie"]) == 1
    # dodatkowe foldery tylko istniejące
    zle = g(f"/api/podroze?t={t}", metoda="POST", dane=json.dumps({"korzenie": ["/nie/ma/takiego"]}).encode())
    assert zle[0] == 400 and b"Nie ma takiego folderu" in zle[1]


def test_podroze_nie_przez_serwer_telefonu(tmp_path):
    """Historia lokalizacji zostaje na komputerze: pełny program z telefonu (po PIN-ie) nie przekazuje /podroze/."""
    import http.cookiejar
    serwer, url, stan = aplikacja.uruchom_serwer(tmp_path / "dane")
    threading.Thread(target=serwer.serve_forever, daemon=True).start()
    s = galeria.SerwerGalerii(stan.galeria("wszystko"), port=0, pin="1357", host="127.0.0.1",
                              pilot=pilot.Pilot(stan, sterowanie=True), galerie=stan.galeria).start()
    try:
        b = f"http://127.0.0.1:{s.port}"
        kl = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        kl.open(urllib.request.Request(b + "/api/g/zaloguj", data=json.dumps({"pin": "1357"}).encode(),
                                       headers={"Content-Type": "application/json"}))
        for sc in ("/podroze/", "/podroze/api/version", "/podroze/sample-trips.json"):
            with pytest.raises(urllib.error.HTTPError) as e:
                kl.open(b + sc)
            assert e.value.code == 403, sc
    finally:
        s.stop()
        serwer.shutdown()
