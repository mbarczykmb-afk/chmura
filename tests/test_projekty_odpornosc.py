"""Projekt nie może stracić nazwy/notatek przez chwilowo nieczytelny projekt.json (Windows) — i usunięty da się przywrócić."""
import pathlib
from unittest import mock

import pytest

from katalogator import projekty


def _projekt(tmp_path):
    P = projekty.Projekty(tmp_path)
    pid = P.nowy("nowy claude")
    P.zapisz(pid, {"nazwa": "Michał", "notatki": "moje", "dom": "Olkusz", "cel": "U:\\Uporządkowane"})
    return P, pid


def test_chwilowa_blokada_pliku_nie_kasuje_nazwy(tmp_path):
    P, pid = _projekt(tmp_path)
    prawdziwe, licz = pathlib.Path.read_text, {"n": 0}

    def czasem(self, *a, **k):
        if self.name == "projekt.json" and licz["n"] < 2:   # dwie pierwsze próby: plik zablokowany
            licz["n"] += 1
            raise PermissionError(32, "plik używany przez inny proces")
        return prawdziwe(self, *a, **k)
    with mock.patch.object(pathlib.Path, "read_text", czasem):
        P.zapisz(pid, {"cel": "U:\\Nowe"})
    w = P.wczytaj(pid)
    assert (w["nazwa"], w["notatki"], w["dom"], w["cel"]) == ("Michał", "moje", "Olkusz", "U:\\Nowe")


def test_trwale_nieczytelny_plik_nie_jest_nadpisywany(tmp_path):
    P, pid = _projekt(tmp_path)

    def zawsze(self, *a, **k):
        raise PermissionError(32, "zablokowany")
    with mock.patch.object(pathlib.Path, "read_text", zawsze), pytest.raises(OSError):
        P.zapisz(pid, {"cel": "U:\\Nowe"})
    assert P.wczytaj(pid)["nazwa"] == "Michał"


def test_uszkodzony_plik_wraca_z_kopii(tmp_path):
    P, pid = _projekt(tmp_path)
    P.zapisz(pid, {"cel": "U:\\Nowe"})   # tworzy projekt.json.bak z poprzednią wersją
    (tmp_path / "projekty" / pid / "projekt.json").write_text("{uszkodzony", encoding="utf-8")
    assert P.wczytaj(pid)["nazwa"] == "Michał"


def test_usuniety_projekt_mozna_przywrocic(tmp_path):
    P, pid = _projekt(tmp_path)
    P.usun(pid)
    assert pid not in [p["id"] for p in P.lista()]
    kosz = P.usuniete()
    assert kosz and kosz[0]["nazwa"] == "Michał"
    nowy = P.przywroc(kosz[0]["klucz"])
    assert P.wczytaj(nowy)["nazwa"] == "Michał" and not P.usuniete()
    with pytest.raises(ValueError):
        P.przywroc("../../etc")


def test_ustawienia_programu_nie_znikaja_przy_blokadzie(tmp_path):
    from katalogator import aktualizacje
    aktualizacje.zapisz_ustawienia(tmp_path, pin="123456", most={"klucz": "abc"})
    prawdziwe = pathlib.Path.read_text

    def zawsze(self, *a, **k):
        if self.name == "program.json":
            raise PermissionError(32, "zablokowany")
        return prawdziwe(self, *a, **k)
    with mock.patch.object(pathlib.Path, "read_text", zawsze), pytest.raises(OSError):
        aktualizacje.zapisz_ustawienia(tmp_path, kopia_ostatnia=1)
    (tmp_path / "program.json").write_text("{pół", encoding="utf-8")   # np. zanik prądu w trakcie zapisu
    assert aktualizacje._ustawienia(tmp_path)["pin"] == "123456"   # z kopii .bak
    aktualizacje.zapisz_ustawienia(tmp_path, motyw="dark")
    d = aktualizacje._ustawienia(tmp_path)
    assert d["pin"] == "123456" and d["most"] == {"klucz": "abc"} and d["motyw"] == "dark"


def test_kosz_projektow_trzyma_dziesiec_najnowszych_usuniec(tmp_path):
    import os
    P = projekty.Projekty(tmp_path)
    stary = P.nowy("stary")
    os.utime(tmp_path / "projekty" / stary, (1, 1))   # dawno nieruszany folder
    for i in range(10):
        P.usun(P.nowy(f"p{i}"))
        kosz = tmp_path / "projekty" / "_kosz"
        for k in kosz.iterdir():   # różne sekundy w nazwach
            pass
    import time as _t
    _t.sleep(1.1)
    P.usun(stary)
    assert any(u["nazwa"] == "stary" for u in P.usuniete())


def test_blokada_plikow_miedzy_procesami(tmp_path):
    import subprocess
    import sys
    import textwrap
    (tmp_path / "p").mkdir()
    kod = textwrap.dedent(f"""
        import sys, time; sys.path.insert(0, {str(pathlib.Path(__file__).resolve().parents[1])!r})
        from katalogator import projekty
        with projekty.blokada_plikow({str(tmp_path / 'p')!r}):
            print('mam', flush=True); time.sleep(3)
    """)
    inny = subprocess.Popen([sys.executable, "-c", kod], stdout=subprocess.PIPE, text=True)
    assert inny.stdout.readline().strip() == "mam"
    with pytest.raises(projekty.Zajety):
        with projekty.blokada_plikow(tmp_path / "p"):
            pass
    inny.wait()
    with projekty.blokada_plikow(tmp_path / "p"):   # po zakończeniu tamtego — wolne
        pass


def test_smieci_po_sciezce_nie_dla_zdjec_z_aparatu():
    from katalogator import kategorie
    p = {"sciezka": "D:/Zdjęcia/tmp/IMG_1.jpg", "wzgledna": "tmp/IMG_1.jpg", "rozmiar": 3_000_000, "rodzaj": "zdjecie"}
    assert kategorie.smieci(p) == "miniatury / pamięć podręczna"
    assert kategorie.smieci({**p, "aparat": "SM-S911B"}) is None
    assert kategorie.smieci({**p, "lat": 50.0}) is None


def test_oproznianie_kosza_nie_rusza_wlasnych_folderow(tmp_path):
    from katalogator import skaner, sprzatanie
    (tmp_path / "Odłożone" / "Duplikaty").mkdir(parents=True)
    (tmp_path / "Odłożone" / "Duplikaty" / "a.jpg").write_bytes(b"x")
    (tmp_path / "Odłożone" / "Wakacje 2019").mkdir()
    (tmp_path / "Odłożone" / "Wakacje 2019" / "moje.jpg").write_bytes(b"y")
    db = skaner.otworz_baze(tmp_path / "k.db")
    sprzatanie.usun_odlozone(db, [str(tmp_path)])
    assert not (tmp_path / "Odłożone" / "Duplikaty" / "a.jpg").exists()
    assert (tmp_path / "Odłożone" / "Wakacje 2019" / "moje.jpg").exists()


def test_usuniecie_rozsylane_do_innej_bazy(tmp_path):
    from katalogator import lokalizacja, skaner
    db = skaner.otworz_baze(tmp_path / "inna.db")
    for n in ("jest.jpg", "zniknal.jpg"):
        db.execute("INSERT INTO pliki(sciezka, korzen, wzgledna, rozmiar, mtime, rodzaj, rozszerzenie, skan) VALUES (?,?,?,?,?,?,?,?)",
                   (str(tmp_path / n), str(tmp_path), n, 1, 1.0, "zdjecie", ".jpg", 1))
    db.commit(); db.close()
    (tmp_path / "jest.jpg").write_bytes(b"x")
    n = lokalizacja.rozeslij_usuniecie(tmp_path / "inna.db", [str(tmp_path / "jest.jpg"), str(tmp_path / "zniknal.jpg")])
    assert n == 1   # plik, który jest na dysku, zostaje w bazie
    db = skaner.otworz_baze(tmp_path / "inna.db")
    assert [r[0] for r in db.execute("SELECT wzgledna FROM pliki")] == ["jest.jpg"]


def test_kopia_zachowuje_poprzednia_wersje(tmp_path):
    import os
    from katalogator import kopia
    bib, kop = tmp_path / "bib", tmp_path / "kop"
    (bib / "2020").mkdir(parents=True)
    (bib / "2020" / "a.jpg").write_bytes(b"dobra wersja")
    kopia.kopiuj(str(bib), str(kop))
    (bib / "2020" / "a.jpg").write_bytes(b"uszk")          # plik w bibliotece obcięty / zmieniony
    os.utime(bib / "2020" / "a.jpg", (2_000_000_000, 2_000_000_000))
    kopia.kopiuj(str(bib), str(kop))
    assert (kop / "2020" / "a.jpg").read_bytes() == b"uszk"
    assert (kop / kopia.FOLDER_POPRZEDNICH / "2020" / "a.jpg").read_bytes() == b"dobra wersja"


def test_nazwy_zarezerwowane_windows():
    from katalogator import planista
    assert planista.czysta_nazwa("CON") == "_CON" and planista.czysta_nazwa("nul.jpg") == "_nul.jpg"
    assert planista.czysta_nazwa("Console") == "Console" and planista.czysta_nazwa("com10") == "com10"


def test_sprawdzanie_wykrywa_zniknale_pliki(tmp_path):
    import os
    import shutil
    from katalogator import kopia
    bib, kop = tmp_path / "bib", tmp_path / "kop"
    (bib / "2020").mkdir(parents=True)
    from PIL import Image
    for i, n in enumerate(("przeniesiony.jpg", "do_kosza.jpg", "usuniety.jpg", "zostaje.jpg")):
        Image.new("RGB", (40 + i, 30), (i * 60, 100, 50)).save(bib / "2020" / n)
    kopia.kopiuj(str(bib), str(kop))
    db = kopia.baza(tmp_path)
    kopia.sprawdz(db, str(bib), str(kop))
    (bib / "Inne").mkdir()
    shutil.move(bib / "2020" / "przeniesiony.jpg", bib / "Inne" / "przeniesiony.jpg")        # przeniesiony w bibliotece
    (bib / "Odłożone" / "Usunięte").mkdir(parents=True)
    shutil.move(bib / "2020" / "do_kosza.jpg", bib / "Odłożone" / "Usunięte" / "do_kosza.jpg")  # odłożony przez program
    os.remove(bib / "2020" / "usuniety.jpg")                                                   # usunięty poza programem
    w = kopia.sprawdz(db, str(bib), str(kop), co_dni=1000)
    pr = {os.path.basename(p["sciezka"]): p for p in kopia.problemy(db)}
    assert w["zniknely"] == 1 and set(pr) == {"usuniety.jpg"} and pr["usuniety.jpg"]["rodzaj"] == "zniknal"
    assert db.execute("SELECT COUNT(*) FROM sumy WHERE sciezka LIKE '%Inne%przeniesiony.jpg'").fetchone()[0] == 1
    assert kopia.przywroc(db, str(bib), str(kop), pr["usuniety.jpg"]["sciezka"])["ok"]
    assert (bib / "2020" / "usuniety.jpg").read_bytes() == (kop / "2020" / "usuniety.jpg").read_bytes()


def test_szybki_skan_widzi_tylko_zmienione_foldery(tmp_path):
    """⚡ „Dograj nowe”: po pełnym skanie sprawdza daty folderów i czyta tylko te ze zmianami."""
    import os
    import time
    from PIL import Image
    from katalogator import skaner
    k = tmp_path / "zdj"
    for rok in ("2023", "2024"):
        (k / rok / "lato").mkdir(parents=True)
        Image.new("RGB", (30, 20), (10, 20, 30)).save(k / rok / "lato" / f"a_{rok}.jpg")
    db = skaner.otworz_baze(tmp_path / "k.db")
    assert skaner.skanuj(str(k), db, szybko=True, wypisz=lambda *_: None).get("szybko_niemozliwe")   # jeszcze nie było pełnego
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    assert db.execute("SELECT COUNT(*) FROM foldery_skan").fetchone()[0] == 5          # korzeń, 2 lata, 2 × „lato”
    w = skaner.skanuj(str(k), db, szybko=True, wypisz=lambda *_: None)
    assert w["wszystkie"] == 0 and w["nowe_lub_zmienione"] == 0                         # nic się nie zmieniło — nic nie przejrzane
    time.sleep(0.05)
    Image.new("RGB", (30, 20), (90, 20, 30)).save(k / "2024" / "lato" / "nowe.jpg")      # nowe zdjęcie w znanym folderze
    (k / "2025" / "wyjazd").mkdir(parents=True)                                          # nowy folder z podfolderem
    Image.new("RGB", (30, 20), (1, 2, 3)).save(k / "2025" / "wyjazd" / "z_nowego.jpg")
    os.utime(k, None)
    w = skaner.skanuj(str(k), db, szybko=True, wypisz=lambda *_: None)
    nazwy = {r[0] for r in db.execute("SELECT wzgledna FROM pliki")}
    assert w["nowe_lub_zmienione"] == 2 and os.path.join("2024", "lato", "nowe.jpg") in nazwy
    assert os.path.join("2025", "wyjazd", "z_nowego.jpg") in nazwy and len(nazwy) == 4
    assert db.execute("SELECT COUNT(*) FROM foldery_skan WHERE folder LIKE '%wyjazd'").fetchone()[0] == 1
    os.remove(k / "2023" / "lato" / "a_2023.jpg")                                        # usunięcia wykrywa dopiero pełny skan
    skaner.skanuj(str(k), db, szybko=True, wypisz=lambda *_: None)
    assert len(list(db.execute("SELECT 1 FROM pliki"))) == 4
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    assert len(list(db.execute("SELECT 1 FROM pliki"))) == 3


def test_przegladarka_dograj_nowe_i_podsumowanie(tmp_path):
    import shutil
    import time
    from PIL import Image
    from test_katalogator import _jpg_z_exif
    from katalogator import przegladarka
    k = tmp_path / "zdj"
    (k / "2025").mkdir(parents=True)
    _jpg_z_exif(k / "2025" / "a.jpg", data="2025:08:01 12:00:00", gps=(50.0, 19.9))
    pr = przegladarka.Przegladarka(tmp_path / "dane")
    pr.ustaw_foldery([str(k)])

    def czekaj():
        for _ in range(200):
            if not pr.stan["trwa"]:
                return
            time.sleep(0.05)
    assert pr.skanuj() is None
    czekaj()
    assert pr.stan["po_skanie"] is None                                    # pierwszy skan — nie ma czego zgłaszać
    time.sleep(0.05)
    shutil.copy(k / "2025" / "a.jpg", k / "2025" / "a - kopia.jpg")       # duplikat
    _jpg_z_exif(k / "2025" / "nowe.jpg", data="2025:09:01 10:00:00", gps=None)   # bez GPS
    (k / "2025" / "zepsute.jpg").write_bytes(b"nie obraz")                # nieczytelne
    assert pr.skanuj(szybko=True) is None
    czekaj()
    po = pr.stan["po_skanie"]
    assert "dograno 3 nowych" in pr.stan["komunikat"], pr.stan["komunikat"]
    assert po["nowe"] == 3 and po["kategorie"]["duplikaty"] == 1 and po["kategorie"]["bez_gps"] == 1 and po["kategorie"]["nieczytelne"] == 1
    for kat, n in (("nowe", 3), ("duplikaty", 1), ("bez_gps", 1), ("nieczytelne", 1)):
        assert pr.galeria.po_skanie(kat)["razem"] == n
    assert pr.galeria.po_skanie("duplikaty")["pliki"][0]["nazwa"] == "a - kopia.jpg"
    assert pr.galeria.po_skanie("zle")["blad"]
    assert pr.skanuj(szybko=True) is None                                  # nic nowego
    czekaj()
    assert pr.stan["po_skanie"]["nowe"] == 0


def test_brak_plikow_interfejsu_daje_czytelna_strone(tmp_path, monkeypatch):
    """Zamiast surowego JSON-a „FileNotFoundError … index.html” — strona z instrukcją naprawy (instalacja niepełna)."""
    import http.client
    import threading
    from katalogator import aktualizacje, aplikacja
    (tmp_path / "dane").mkdir()
    aktualizacje.zapisz_ustawienia(tmp_path / "dane", powitanie_widziane=True)
    serwer, url, _ = aplikacja.uruchom_serwer(tmp_path / "dane")
    threading.Thread(target=serwer.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(aplikacja, "UI", tmp_path / "nie-ma-ui")
        host, port = url.split("//")[1].split("/")[0].split(":")
        c = http.client.HTTPConnection(host, int(port), timeout=10)
        c.request("GET", "/?t=" + url.split("t=")[1])
        r = c.getresponse()
        tresc = r.read().decode("utf-8")
        assert r.status == 503 and "Instalacja Katalogatora jest niepełna" in tresc and "releases/latest" in tresc
    finally:
        serwer.shutdown()
