"""Stabilizator: przerwy w dostępie do dysku, tempo i czas do końca, duże biblioteki."""

import os
import threading
import time

import pytest

from katalogator import analiza, planista, skaner, stabilnosc, wykonawca
from katalogator.skaner import Przerwano


def _zniknij_na_chwile(folder, po=0.3, na=1.0):
    """Symuluje zerwane połączenie z dyskiem sieciowym: folder znika i po chwili wraca."""
    ukryty = str(folder) + ".offline"

    def f():
        time.sleep(po)
        os.rename(folder, ukryty)
        time.sleep(na)
        os.rename(ukryty, folder)
    t = threading.Thread(target=f)
    t.start()
    return t


def test_straznik_czeka_na_powrot_dysku(tmp_path):
    dysk = tmp_path / "nas"
    dysk.mkdir()
    (dysk / "a.txt").write_text("x")
    komunikaty = []
    s = stabilnosc.Straznik([dysk], zglos=komunikaty.append, sprawdzaj_co=0.1)
    t = _zniknij_na_chwile(dysk, po=0, na=0.6)
    time.sleep(0.1)
    wynik = s.wykonaj(lambda: (dysk / "a.txt").read_text(), str(dysk / "a.txt"))
    t.join()
    assert wynik == "x" and s.przerwy == 1
    assert any(k and "czekam" in k for k in komunikaty) and komunikaty[-1] is None


def test_straznik_nie_czeka_przy_bledzie_pliku(tmp_path):
    s = stabilnosc.Straznik([tmp_path], sprawdzaj_co=0.1)
    t0 = time.time()
    with pytest.raises(FileNotFoundError):
        s.wykonaj(open, str(tmp_path / "brak.txt"), str(tmp_path / "brak.txt"))
    assert time.time() - t0 < 1 and s.przerwy == 0


def test_straznik_poddaje_sie_po_limicie_i_da_sie_przerwac(tmp_path):
    brak = tmp_path / "odlaczony"
    s = stabilnosc.Straznik([brak], czekaj_maks=0.3, sprawdzaj_co=0.1)
    with pytest.raises(OSError, match="Postęp jest zapisany"):
        s.czekaj_na(str(brak))
    ev = threading.Event()
    ev.set()
    with pytest.raises(Przerwano):
        stabilnosc.Straznik([brak], ev, sprawdzaj_co=0.1).czekaj_na(str(brak))


def test_tempo_liczy_czas_do_konca():
    t = stabilnosc.Tempo()
    t.start = 1000
    for i in range(11):
        t.dodaj(i / 100, i * 10, i * 1_000_000, teraz=1000 + i)  # 1% na sekundę
    w = t.wynik(teraz=1010)
    assert w["uplynelo"] == 10 and w["plikow_s"] == 10 and w["bajty_s"] == 1_000_000
    assert 85 <= w["eta"] <= 95


def test_skan_nie_usuwa_wynikow_nieczytelnego_folderu(tmp_path, monkeypatch):
    k = tmp_path / "k"
    (k / "A").mkdir(parents=True)
    (k / "B").mkdir()
    (k / "A" / "1.txt").write_text("a")
    (k / "B" / "2.txt").write_text("b")
    db = skaner.otworz_baze(":memory:")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    prawdziwy = os.scandir

    def zepsuty(p):
        if os.path.basename(p) == "B":
            raise PermissionError(13, "brak dostępu", p)
        return prawdziwy(p)
    monkeypatch.setattr(skaner.os, "scandir", zepsuty)
    w = skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    assert w["nieczytelne"] and w["usuniete_z_bazy"] == 0
    assert db.execute("SELECT COUNT(*) FROM pliki").fetchone()[0] == 2


def test_skan_podaje_liczbe_plikow_do_paska(tmp_path):
    k = tmp_path / "k"
    k.mkdir()
    for i in range(30):
        (k / f"{i}.txt").write_text(str(i))
    db = skaner.otworz_baze(":memory:")
    zdarzenia = []
    skaner.skanuj(str(k), db, postep=lambda n, gdzie, wszystkie=0, etap="": zdarzenia.append((etap, n, wszystkie)))
    assert ("odczyt metadanych", 30, 30) in zdarzenia


def test_wykonanie_przetrwa_zerwanie_polaczenia(tmp_path, monkeypatch):
    zr = tmp_path / "nas"
    cel = tmp_path / "cel"
    zr.mkdir()
    cel.mkdir()
    for i in range(6):
        (zr / f"plik{i}.pdf").write_bytes(os.urandom(2000 + i))
    db = skaner.otworz_baze(":memory:")
    skaner.skanuj(str(zr), db, wypisz=lambda *_: None)
    planista.generuj(db, [{"sciezka": str(zr), "tryb": "kopiuj"}], str(cel))
    prawdziwe = wykonawca.kopiuj_z_weryfikacja
    licznik = {"n": 0}
    stan = {}

    def kopiuj(z, c, *a, **kw):  # przy 3. pliku „zrywa się sieć”
        licznik["n"] += 1
        if licznik["n"] == 3:
            stan["watek"] = _zniknij_na_chwile(zr, po=0, na=0.5)
            time.sleep(0.1)
            raise OSError(64, "Określona nazwa sieciowa nie jest już dostępna")
        return prawdziwe(z, c, *a, **kw)
    monkeypatch.setattr(wykonawca, "kopiuj_z_weryfikacja", kopiuj)
    czeka = []

    def postep(*a, **kw):
        pass
    postep.czeka = czeka.append
    orig = stabilnosc.Straznik.__init__

    def init(self, *a, **kw):
        orig(self, *a, **kw)
        self.sprawdzaj_co = 0.1
    monkeypatch.setattr(stabilnosc.Straznik, "__init__", init)
    w = wykonawca.wykonaj(db, postep=postep)
    stan["watek"].join()
    assert w["zrobione"] == 6 and w["bledy"] == 0
    assert len(list(cel.rglob("*.pdf"))) == 6
    assert any(czeka) and czeka[-1] is None


def test_grupy_podobnych_szybkie_i_ograniczone(tmp_path):
    """Setki niemal jednakowych ujęć (timelapse) nie mogą zawiesić programu."""
    import random
    db = skaner.otworz_baze(":memory:")
    analiza.przygotuj(db)
    random.seed(5)
    baza = random.getrandbits(64) | (1 << 20) | 0xFF
    podpis = bytes(random.randrange(256) for _ in range(112)).hex()
    for i in range(600):
        h = baza ^ (1 << (i % 3))
        db.execute("INSERT INTO pliki VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (f"/x/{i}.jpg", "/x", f"{i}.jpg", 1000 + i, 1.0, "zdjecie", ".jpg", None, None, None, None,
                    None, None, None, None, None, 1))
        db.execute("INSERT INTO analiza(sciezka, rozmiar, mtime, dhash, podpis, szer, wys, ostrosc) "
                   "VALUES (?,?,?,?,?,1,1,1)", (f"/x/{i}.jpg", 1000 + i, 1.0, f"{h:016x}", podpis))
    db.commit()
    t0 = time.time()
    g = analiza.grupy_podobnych(db)
    assert time.time() - t0 < 5
    assert g and max(len(x) for x in g) <= analiza.MAKS_SASIADOW + 1
    t0 = time.time()
    assert analiza.grupy_podobnych(db) is g and time.time() - t0 < 0.1  # drugi raz z pamięci


def test_otwarcie_bazy_gdy_skan_zapisuje(tmp_path):
    """Zgłoszone „database is locked”: okno otwiera bazę, gdy skan w tle trzyma transakcję zapisu."""
    baza = tmp_path / "k.db"
    skaner.otworz_baze(baza).close()
    trzyma = threading.Event()

    def skan():  # jak skaner: długa transakcja zapisu we własnym wątku
        zapis = skaner.otworz_baze(baza)
        zapis.execute("BEGIN IMMEDIATE")
        zapis.execute("INSERT INTO skany(korzen, start) VALUES ('x', 0)")
        trzyma.set()
        time.sleep(0.5)
        zapis.commit()
        zapis.close()
    t = threading.Thread(target=skan)
    t.start()
    trzyma.wait()
    db = skaner.otworz_baze(baza)  # nie może się wywrócić
    assert db.execute("SELECT COUNT(*) FROM pliki").fetchone()[0] == 0
    t.join()


def test_swieza_baza_otwierana_naraz(tmp_path):
    """Nowy projekt: okno i skan otwierają nieistniejącą jeszcze bazę w tej samej chwili
    (przełączanie na WAL wywracało się z „database is locked” — kilka razy na kilkaset prób)."""
    bledy = []
    for runda in range(40):
        baza = tmp_path / f"k{runda}.db"
        start = threading.Barrier(8)

        def otworz():
            start.wait()
            try:
                db = skaner.otworz_baze(baza)
                db.execute("SELECT COUNT(*) FROM pliki").fetchone()
                db.close()
            except Exception as e:  # pragma: no cover - raport błędu
                bledy.append(repr(e))
        watki = [threading.Thread(target=otworz) for _ in range(8)]
        for w in watki:
            w.start()
        for w in watki:
            w.join()
    assert not bledy, bledy[:3]


def _porzadkuj(zrodlo, cel, db_plik):
    from katalogator import planista
    db = skaner.otworz_baze(db_plik)
    skaner.skanuj(str(zrodlo), db, wypisz=lambda *_: None)
    planista.generuj(db, [{"sciezka": str(zrodlo), "tryb": "przenies"}], str(cel), dom="Olkusz")
    return db, wykonawca.wykonaj(db)


def test_ten_sam_folder_pod_dwiema_nazwami_nic_nie_znika(tmp_path):
    """Źródło Z:\\Biblioteka i cel \\\\NAS\\Biblioteka to ten sam folder: „przenieś” nie może usunąć jedynej kopii."""
    from test_katalogator import _jpg_z_exif
    bib = tmp_path / "Biblioteka"
    f = bib / "Zdjęcia" / "Zdjęcia z 2023" / "Marzec w domu"
    f.mkdir(parents=True)
    _jpg_z_exif(f / "IMG_20230310.jpg", data="2023:03:10 12:00:00")
    druga_nazwa = tmp_path / "NAS_Biblioteka"
    try:
        os.symlink(bib, druga_nazwa, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("dowiązania symboliczne wymagają uprawnień (Windows bez trybu dewelopera)")
    db, w = _porzadkuj(bib, druga_nazwa, tmp_path / "k.db")
    assert (f / "IMG_20230310.jpg").exists()
    assert len(list(bib.rglob("*.jpg"))) == 1


def test_sprzatanie_nie_rusza_cudzych_folderow_ani_nie_wychodzi_poza_zrodlo(tmp_path):
    from test_katalogator import _jpg_z_exif
    nad = tmp_path / "Zdjecia_stare"          # folder nad wybranym źródłem
    zr = nad / "2019"
    (zr / "wakacje" / ".prywatne").mkdir(parents=True)
    (zr / "wakacje" / ".prywatne" / "notatka.txt").write_text("ważne", encoding="utf-8")
    (zr / "wakacje" / "Odłożone").mkdir()
    (zr / "wakacje" / "Odłożone" / "moje.txt").write_text("też ważne", encoding="utf-8")
    (zr / "inne").mkdir()
    (zr / "inne" / "Thumbs.db").write_bytes(b"x")
    _jpg_z_exif(zr / "wakacje" / "IMG_1.jpg", data="2019:07:10 12:00:00")
    _jpg_z_exif(zr / "inne" / "IMG_2.jpg", data="2019:07:11 12:00:00")
    db, w = _porzadkuj(zr, tmp_path / "Biblioteka", tmp_path / "k.db")
    assert w["zrobione"] == 2
    assert (zr / "wakacje" / ".prywatne" / "notatka.txt").read_text(encoding="utf-8") == "ważne"
    assert (zr / "wakacje" / "Odłożone" / "moje.txt").exists()
    assert not (zr / "inne").exists()      # pusty (tylko Thumbs.db) — sprzątnięty
    assert nad.exists()                    # nigdy ponad wybrany folder


def test_ten_sam_plik_rozpoznany():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.jpg")
        open(p, "wb").write(b"x")
        assert wykonawca._ten_sam_plik(p, os.path.join(d, ".", "a.jpg"))
        assert not wykonawca._ten_sam_plik(p, os.path.join(d, "b.jpg"))


def test_plik_chwilowo_otwarty_ponawiany(tmp_path, monkeypatch):
    """Windows: plik otwarty przez inny program (WinError 32) — porządkowanie czeka i próbuje jeszcze raz."""
    zr, cel = tmp_path / "nas", tmp_path / "cel"
    zr.mkdir()
    cel.mkdir()
    (zr / "umowa.pdf").write_bytes(b"%PDF" * 50)
    db = skaner.otworz_baze(":memory:")
    skaner.skanuj(str(zr), db, wypisz=lambda *_: None)
    planista.generuj(db, [{"sciezka": str(zr), "tryb": "przenies"}], str(cel))
    prawdziwe, licznik = wykonawca._wykonaj_plik, {"n": 0}

    def zajety(*a, **kw):
        licznik["n"] += 1
        if licznik["n"] == 1:
            e = PermissionError(13, "Proces nie może uzyskać dostępu do pliku")
            e.winerror = 32
            raise e
        return prawdziwe(*a, **kw)
    monkeypatch.setattr(wykonawca, "_wykonaj_plik", zajety)
    monkeypatch.setattr(wykonawca.time, "sleep", lambda s: None)
    w = wykonawca.wykonaj(db)
    assert w["zrobione"] == 1 and w["bledy"] == 0 and licznik["n"] == 2


def test_pamiec_miniatur_przycinana(tmp_path):
    from katalogator import galeria
    g = galeria.Galeria(tmp_path / "k.db", pamiec_min=tmp_path / "min")
    (tmp_path / "min" / "00").mkdir(parents=True)
    for i in range(10):
        p = tmp_path / "min" / "00" / f"{i}.jpg"
        p.write_bytes(b"x" * 1000)
        os.utime(p, (1000 + i, 1000 + i))
    g.MAKS_PAMIEC_MIN = 5000
    g._przytnij_pamiec()
    zostaly = sorted(p.name for p in (tmp_path / "min").rglob("*.jpg"))
    assert len(zostaly) == 4 and "9.jpg" in zostaly and "0.jpg" not in zostaly  # najdawniej używane poszły


def test_duze_pliki_liczone_po_jednym(tmp_path, monkeypatch):
    """Pełny odcisk dużych plików — po jednym naraz (dysk sieciowy z talerzem), małe nadal równolegle."""
    import threading as th
    import time as t
    from katalogator import duplikaty, skaner
    k = tmp_path / "d"
    k.mkdir()
    for i in range(6):  # 3 pary identycznych „dużych” plików
        (k / f"duzy{i}.bin").write_bytes(bytes([i // 2]) * (3 << 20))  # > 2 MB: potrzebny pełny odcisk
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    monkeypatch.setattr(duplikaty, "DUZY_PLIK", 1 << 20)
    teraz, maks, blok = [0], [0], th.Lock()
    oryg = duplikaty._odcisk

    def wolny(sciezka, rozmiar, pelny, *a, **kw):
        if pelny:
            with blok:
                teraz[0] += 1
                maks[0] = max(maks[0], teraz[0])
            t.sleep(0.05)
            with blok:
                teraz[0] -= 1
        return oryg(sciezka, rozmiar, pelny, *a, **kw)
    monkeypatch.setattr(duplikaty, "_odcisk", wolny)
    w = duplikaty.szukaj(db)
    assert w["grupy"] == 3 and maks[0] == 1
