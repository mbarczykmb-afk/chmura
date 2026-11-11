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
