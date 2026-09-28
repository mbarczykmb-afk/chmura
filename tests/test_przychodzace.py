import sys

import pytest

from katalogator import przychodzace, projekty
from test_katalogator import _jpg_z_exif

OLKUSZ, HEL = (50.2811, 19.5625), (54.6080, 18.8010)


@pytest.fixture
def uklad(tmp_path):
    proj = projekty.Projekty(tmp_path / "dane")
    pid = proj.nowy("Test")
    inbox = tmp_path / "Z telefonu"
    bib = tmp_path / "Biblioteka"
    (inbox / "DCIM").mkdir(parents=True)
    bib.mkdir()
    _jpg_z_exif(inbox / "DCIM" / "IMG_1.jpg", data="2026:09:10 12:00:00", gps=HEL)
    _jpg_z_exif(inbox / "DCIM" / "IMG_2.jpg", data="2026:09:12 12:00:00", gps=OLKUSZ)
    from PIL import Image
    Image.new("RGB", (8, 8)).save(inbox / "bez_daty.png")  # data tylko z pliku -> zostaje
    proj.zapisz(pid, {"przychodzace": [str(inbox)], "cel": str(bib), "dom": "Olkusz"})
    return proj, pid, inbox, bib


def test_sprawdz_i_przenies(uklad):
    proj, pid, inbox, bib = uklad
    s = przychodzace.sprawdz(proj, pid)
    assert s["przenies"] == 2 and s["pominiete"] == 1
    foldery = {f["folder"] for f in s["foldery"]}
    assert foldery == {"Zdjęcia/Zdjęcia z 2026/Wrzesień na Helu", "Zdjęcia/Zdjęcia z 2026/Wrzesień w domu"}
    assert not list(bib.rglob("*.jpg"))  # sprawdzenie niczego nie przenosi
    w = przychodzace.wykonaj(proj, pid)
    assert w["zrobione"] == 2
    assert (bib / "Zdjęcia" / "Zdjęcia z 2026" / "Wrzesień na Helu" / "IMG_1.jpg").exists()
    assert not (inbox / "DCIM").exists() and (inbox / "bez_daty.png").exists()  # pusty podfolder sprzątnięty
    # ten sam plik zrzucony drugi raz nie tworzy kopii (2)
    import shutil
    (inbox / "DCIM").mkdir()
    shutil.copy2(bib / "Zdjęcia" / "Zdjęcia z 2026" / "Wrzesień na Helu" / "IMG_1.jpg", inbox / "DCIM" / "IMG_1.jpg")
    przychodzace.sprawdz(proj, pid)
    w = przychodzace.wykonaj(proj, pid)
    assert w["zrobione"] == 1 and not list(bib.rglob("IMG_1 (2).jpg")) and not (inbox / "DCIM" / "IMG_1.jpg").exists()
    # cofnięcie: przywraca oryginał do folderu przychodzącego, plik w bibliotece zostaje
    przychodzace.cofnij(proj, pid)
    assert (inbox / "DCIM" / "IMG_1.jpg").exists()
    assert (bib / "Zdjęcia" / "Zdjęcia z 2026" / "Wrzesień na Helu" / "IMG_1.jpg").exists()


def test_automat_i_dziennik(uklad):
    proj, pid, inbox, bib = uklad
    opis = przychodzace.automat(proj.katalog, pid)
    assert "przeniesiono 2" in opis and "ręcznego przejrzenia: 1" in opis
    assert "przeniesiono 2" in (proj.baza(pid).parent / "auto.log").read_text(encoding="utf-8")
    from katalogator import skaner
    db = skaner.otworz_baze(proj.baza(pid))
    assert projekty.dziennik(db)[0]["typ"] == "auto"
    assert "Brak nowych" in przychodzace.automat(proj.katalog, pid)


def test_bledy_konfiguracji(tmp_path):
    proj = projekty.Projekty(tmp_path)
    pid = proj.nowy("Pusty")
    with pytest.raises(ValueError, match="folder przychodzący"):
        przychodzace.sprawdz(proj, pid)
    assert "Błąd" in przychodzace.automat(tmp_path, pid)


def test_polecenia_harmonogramu(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Programy\Katalogator\Katalogator.exe")
    usun, utworz = przychodzace.polecenia_harmonogramu("moj-abc123", "21:00")
    assert usun[:3] == ["schtasks", "/Delete", "/F"]
    assert utworz[utworz.index("/ST") + 1] == "21:00"
    assert utworz[-1] == r'"C:\Programy\Katalogator\Katalogator.exe" --auto moj-abc123'
    assert przychodzace.polecenia_harmonogramu("moj-abc123", "") == [usun]
    with pytest.raises(ValueError):
        przychodzace.polecenia_harmonogramu("moj-abc123", "25:00")


def test_auto_bez_konsoli_z_polskimi_znakami(tmp_path, monkeypatch):
    """Katalogator.exe --auto: brak konsoli, a domyślne kodowanie nie zna polskich znaków."""
    import io
    from katalogator.__main__ import main
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    wynik = main(["--auto", "nie-ma-takiego"])
    assert wynik == 0
    log = (tmp_path / "Katalogator" / "logi" / "katalogator.log").read_text(encoding="utf-8")
    assert "Nie ma takiego projektu" in log and "Traceback" not in log
    # konsola w kodowaniu cp1252 też nie może wywrócić programu
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))
    assert main(["--auto", "nie-ma-takiego"]) == 0
