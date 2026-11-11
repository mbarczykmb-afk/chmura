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
