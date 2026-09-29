"""Pojedyncze bardzo duże pliki (filmy po kilkadziesiąt–kilkaset GB): wznawianie kopii, FAT32, metadane."""

import os
import struct
import threading

import pytest

from katalogator import metadane, planista, skaner, typy, wykonawca
from katalogator.skaner import Przerwano


@pytest.fixture
def male_kawalki(monkeypatch):
    """Skala testu: kawałek 4 KB zamiast 64 MB, „duży plik” od 1 bajta."""
    monkeypatch.setattr(wykonawca, "BLOK", 1024)
    monkeypatch.setattr(wykonawca, "KAWALEK", 4096)
    monkeypatch.setattr(wykonawca, "WZNAWIANIE_OD", 1)
    monkeypatch.setattr(wykonawca, "ZAPIS_STANU_CO", 0.0)


def _przerwij_po(n_bajtow):
    ev, licznik = threading.Event(), [0]

    def licz(n):
        licznik[0] += n
        if licznik[0] >= n_bajtow:
            ev.set()
    return ev, licz


def test_przerwana_kopia_rusza_od_miejsca_przerwania(tmp_path, male_kawalki):
    zr, cel = tmp_path / "film.mp4", tmp_path / "cel.mp4"
    dane = os.urandom(50_000)
    zr.write_bytes(dane)
    ev, licz = _przerwij_po(21_000)
    with pytest.raises(Przerwano):
        wykonawca.kopiuj_z_weryfikacja(str(zr), str(cel), ev, licz)
    tmp = str(cel) + wykonawca.TMP
    assert os.path.exists(tmp) and os.path.exists(tmp + wykonawca.STAN) and not cel.exists()
    zliczone = []
    wykonawca.kopiuj_z_weryfikacja(str(zr), str(cel), threading.Event(), zliczone.append)
    assert cel.read_bytes() == dane
    assert zliczone[0] >= 16_384 and zliczone[0] % 4096 == 0  # pominięte, już skopiowane kawałki
    assert sum(zliczone) == 2 * len(dane)  # kopia + sprawdzenie, bez czytania drugi raz początku
    assert not os.path.exists(tmp) and not os.path.exists(tmp + wykonawca.STAN)


def test_uszkodzony_poczatek_wykryty_przy_sprawdzaniu(tmp_path, male_kawalki):
    zr, cel = tmp_path / "film.mp4", tmp_path / "cel.mp4"
    dane = os.urandom(30_000)
    zr.write_bytes(dane)
    ev, licz = _przerwij_po(17_000)
    with pytest.raises(Przerwano):
        wykonawca.kopiuj_z_weryfikacja(str(zr), str(cel), ev, licz)
    tmp = str(cel) + wykonawca.TMP
    with open(tmp, "r+b") as f:  # np. zapis przerwany w połowie przez sieć
        f.seek(100)
        f.write(b"\0" * 10)
    with pytest.raises(OSError, match="różni się"):
        wykonawca.kopiuj_z_weryfikacja(str(zr), str(cel))
    assert not os.path.exists(tmp) and not os.path.exists(tmp + wykonawca.STAN)  # zła kopia nie jest wznawiana
    wykonawca.kopiuj_z_weryfikacja(str(zr), str(cel))
    assert cel.read_bytes() == dane


def test_zmieniony_oryginal_kopiowany_od_nowa(tmp_path, male_kawalki):
    zr, cel = tmp_path / "film.mp4", tmp_path / "cel.mp4"
    zr.write_bytes(os.urandom(30_000))
    ev, licz = _przerwij_po(17_000)
    with pytest.raises(Przerwano):
        wykonawca.kopiuj_z_weryfikacja(str(zr), str(cel), ev, licz)
    nowe = os.urandom(30_000)
    zr.write_bytes(nowe)
    os.utime(zr, (1_600_000_000, 1_600_000_000))
    zliczone = []
    wykonawca.kopiuj_z_weryfikacja(str(zr), str(cel), None, zliczone.append)
    assert cel.read_bytes() == nowe and zliczone[0] <= 1024


def test_maly_plik_nie_zostawia_tymczasowego(tmp_path, monkeypatch):
    monkeypatch.setattr(wykonawca, "BLOK", 1024)
    zr, cel = tmp_path / "a.jpg", tmp_path / "b.jpg"
    zr.write_bytes(os.urandom(10_000))
    ev, licz = _przerwij_po(3000)
    with pytest.raises(Przerwano):
        wykonawca.kopiuj_z_weryfikacja(str(zr), str(cel), ev, licz)
    assert list(tmp_path.iterdir()) == [zr]


def test_wykonanie_wznawia_i_sprzata(tmp_path, male_kawalki, monkeypatch):
    zr, cel = tmp_path / "nas", tmp_path / "cel"
    (zr / "Filmy").mkdir(parents=True)
    dane = {f"VID_2020010{i}_120000.mp4": os.urandom(40_000 + i) for i in range(3)}
    for n, d in dane.items():
        (zr / "Filmy" / n).write_bytes(d)
    db = skaner.otworz_baze(":memory:")
    skaner.skanuj(str(zr), db, wypisz=lambda *_: None)
    planista.generuj(db, [{"sciezka": str(zr), "tryb": "kopiuj"}], str(cel))
    ev = threading.Event()
    licznik = [0]

    class Postep:
        czeka = None

        def __call__(self, etap, zrobione, wszystkie, bajty, **kw):
            licznik[0] = bajty
            if bajty > 10_000:  # w trakcie kopiowania pierwszego filmu
                ev.set()
    zegar = iter(range(0, 10**6))
    monkeypatch.setattr(wykonawca.time, "monotonic", lambda: next(zegar))  # postęp zgłaszany po każdym bloku
    with pytest.raises(Przerwano):
        wykonawca.wykonaj(db, postep=Postep(), przerwij=ev)
    zostawione = [p for p in cel.rglob("*") if p.is_file() and ".katalogator-tmp" in p.name]
    assert zostawione and db.execute("SELECT COUNT(*) FROM niedokonczone").fetchone()[0] == 1
    # przerwana kopia nie trafia do skanu biblioteki
    assert all(typy.pominac_plik(p.name) for p in zostawione)
    w = wykonawca.wykonaj(db)
    assert w["zrobione"] == 3 and w["bledy"] == 0
    assert sorted(p.name for p in cel.rglob("*.mp4")) == sorted(dane)
    for p in cel.rglob("*.mp4"):
        assert p.read_bytes() == dane[p.name]
    assert not [p for p in cel.rglob("*") if ".katalogator-tmp" in p.name]
    assert db.execute("SELECT COUNT(*) FROM niedokonczone").fetchone()[0] == 0


def test_osierocona_przerwana_kopia_usunieta(tmp_path, male_kawalki):
    """Plan zmieniony po przerwaniu (np. plik pominięty) — niedokończona kopia nie zostaje w bibliotece."""
    zr, cel = tmp_path / "nas", tmp_path / "cel"
    zr.mkdir()
    (zr / "VID_20200101_120000.mp4").write_bytes(os.urandom(40_000))
    (zr / "VID_20200102_120000.mp4").write_bytes(os.urandom(40_000))
    db = skaner.otworz_baze(":memory:")
    skaner.skanuj(str(zr), db, wypisz=lambda *_: None)
    planista.generuj(db, [{"sciezka": str(zr), "tryb": "kopiuj"}], str(cel))
    ev, licz = _przerwij_po(10_000)

    class Postep:
        czeka = None

        def __call__(self, etap, zrobione, wszystkie, bajty, **kw):
            if bajty > 10_000:
                ev.set()
    with pytest.raises(Przerwano):
        wykonawca.wykonaj(db, postep=Postep(), przerwij=ev)
    przerwany = db.execute("SELECT id FROM plan WHERE tryb='kopiuj' AND wynik IS NULL ORDER BY id").fetchone()[0]
    db.execute("UPDATE plan SET pominiety=1 WHERE id=?", (przerwany,))
    db.commit()
    wykonawca.wykonaj(db)
    assert not [p for p in cel.rglob("*") if ".katalogator-tmp" in p.name]


def test_fat32_ostrzega_i_nie_probuje(tmp_path, monkeypatch):
    zr, cel = tmp_path / "nas", tmp_path / "usb"
    zr.mkdir()
    (zr / "VID_20200101_120000.mp4").write_bytes(os.urandom(5000))
    (zr / "VID_20200102_120000.mp4").write_bytes(os.urandom(500))
    db = skaner.otworz_baze(":memory:")
    skaner.skanuj(str(zr), db, wypisz=lambda *_: None)
    planista.generuj(db, [{"sciezka": str(zr), "tryb": "kopiuj"}], str(cel))
    monkeypatch.setattr(wykonawca, "system_plikow", lambda s: "fat32")
    monkeypatch.setattr(wykonawca, "MAKS_FAT32", 1000)
    assert wykonawca.sprawdz(db)["za_duze_fat"] == 1
    w = wykonawca.wykonaj(db)
    assert w["zrobione"] == 1 and w["bledy"] == 1
    blad = db.execute("SELECT wynik FROM plan WHERE wynik LIKE 'blad%'").fetchone()[0]
    assert "FAT32" in blad
    monkeypatch.setattr(wykonawca, "system_plikow", lambda s: "exfat")
    assert "za_duze_fat" not in wykonawca.sprawdz(db)


def test_system_plikow_znany():
    assert wykonawca.system_plikow(os.getcwd()) not in wykonawca.FAT


def test_postep_kopiowania_liczy_sprawdzanie(tmp_path, monkeypatch):
    """Pasek i czas do końca uwzględniają drugi odczyt (sprawdzenie kopii) — bez tego czas był zaniżony 2×."""
    monkeypatch.setattr(wykonawca, "BLOK", 1024)
    zr, cel = tmp_path / "nas", tmp_path / "cel"
    zr.mkdir()
    (zr / "VID_20200101_120000.mp4").write_bytes(os.urandom(100_000))
    db = skaner.otworz_baze(":memory:")
    skaner.skanuj(str(zr), db, wypisz=lambda *_: None)
    planista.generuj(db, [{"sciezka": str(zr), "tryb": "kopiuj"}], str(cel))
    probki = []

    class Postep:
        czeka = None

        def __call__(self, etap, zrobione, wszystkie, bajty, **kw):
            probki.append((bajty, kw.get("bajty_razem")))
    monkeypatch.setattr(wykonawca.time, "monotonic", iter(range(0, 10**6, 1)).__next__)
    wykonawca.wykonaj(db, postep=Postep())
    razem = probki[-1][1]
    assert probki[-1][0] == razem == 100_000
    srodek = [b for b, _ in probki if 0 < b < razem]
    assert srodek and max(srodek) >= razem * 0.45  # w połowie pracy (koniec kopiowania) pasek ≈ 50%
    assert min(b for b in srodek if b) < razem * 0.5


def _rzadki_mp4(sciezka, rozmiar_mdat):
    """Film z ogromnym mdat (64-bitowy rozmiar) i moov na końcu — zapisany jako plik rzadki (nie zajmuje miejsca)."""
    ftyp = struct.pack(">I4s", 20, b"ftyp") + b"isom" + b"\0\0\0\1" + b"isom"
    sek = 3_700_000_000  # 2021 r. od 1904
    mvhd = struct.pack(">I4sB3xII", 8 + 12, b"mvhd", 0, sek, sek)
    moov = struct.pack(">I4s", 8 + len(mvhd), b"moov") + mvhd
    with open(sciezka, "wb") as f:
        f.write(ftyp)
        f.write(struct.pack(">I4sQ", 1, b"mdat", 16 + rozmiar_mdat))
        f.seek(rozmiar_mdat, os.SEEK_CUR)
        f.write(moov)


def test_metadane_filmu_400gb_bez_czytania_calosci(tmp_path):
    p = tmp_path / "VID.mp4"
    try:
        _rzadki_mp4(p, 400 * 10**9)
    except OSError:
        pytest.skip("system plików bez plików rzadkich")
    m = metadane.odczytaj(str(p), typy.FILM, p.stat().st_mtime)
    assert m.data and m.data.year == 2021 and m.zrodlo_daty == "film"
