"""🛟 Odzyskiwanie: filtry dla Windows File Recovery, kosze Windows ($I/$R), kopia zapasowa, wyniki."""
import os
import struct
import time

from katalogator import odzyskiwanie as o


def test_filtry_winfr():
    assert o.podziel(r"C:\Users\Ja\Downloads") == ("C:", "\\Users\\Ja\\Downloads\\")
    assert o.podziel("D:\\") == ("D:", "")
    assert o.wzorce("\\Users\\Ja\\Downloads\\", "wszystko", "") == ["\\Users\\Ja\\Downloads\\"]
    assert o.wzorce("", "wszystko", "") == []
    w = o.wzorce("\\Users\\Ja\\Downloads\\", "filmy", "zoom")
    assert "\\Users\\Ja\\Downloads\\*zoom*.mp4" in w and len(w) == len(o.TYPY["filmy"])
    assert o.wzorce("", "wszystko", 'zo"om*') == ["*zoom*"]  # znaki niedozwolone usunięte
    p = o.polecenie("winfr", "C:", "E:\\Odzyskane", True, ["*.mp4"])
    assert p == ["winfr", "C:", "E:\\Odzyskane", "/extensive", "/n", "*.mp4", "/a"]
    assert o.polecenie("winfr", "C:", "E:\\x", False, [])[3] == "/regular"


def test_uruchom_wymaga_innego_dysku(monkeypatch, tmp_path):
    monkeypatch.setattr(o, "winfr", lambda: "winfr.exe")
    assert "INNY dysk" in o.uruchom("C:", "C:\\", "", "wszystko", "", True)["blad"]
    monkeypatch.setattr(o, "winfr", lambda: None)
    assert "zainstaluj" in o.uruchom("C:", "E:\\", "", "wszystko", "", True)["blad"].lower()


def _i(sciezka: str, rozmiar: int, wersja: int = 2) -> bytes:
    ft = int((time.time() + 11644473600) * 10_000_000)
    if wersja == 2:
        n = sciezka + "\0"
        return struct.pack("<qqqi", 2, rozmiar, ft, len(n)) + n.encode("utf-16-le")
    return struct.pack("<qqq", 1, rozmiar, ft) + sciezka.encode("utf-16-le").ljust(520, b"\0")


def test_kosz_windows_i_przywracanie(tmp_path):
    d = tmp_path / "dysk"
    k = d / "$Recycle.Bin" / "S-1-5-21-1"
    k.mkdir(parents=True)
    oryg = str(tmp_path / "Pobrane" / "zoom_0.mp4")
    (k / "$IABC123.mp4").write_bytes(_i(oryg, 5))
    (k / "$RABC123.mp4").write_bytes(b"12345")
    (k / "$IXYZ.jpg").write_bytes(_i(str(tmp_path / "a.jpg"), 3, wersja=1))
    (k / "$RXYZ.jpg").write_bytes(b"abc")
    folder = k / "$RDIR1"
    (folder / "sub").mkdir(parents=True)
    (folder / "sub" / "b.jpg").write_bytes(b"x")
    (k / "$IDIR1").write_bytes(_i(str(tmp_path / "Album"), 1))
    info = o.czytaj_i(_i("C:\\x\\y.txt", 9))
    assert info["oryginal"] == "C:\\x\\y.txt" and info["rozmiar"] == 9 and info["usuniety"]
    wsz = o.kosze_windows([str(d)], "wszystko", "")
    assert {x["nazwa"] for x in wsz} == {"zoom_0.mp4", "a.jpg", "b.jpg"}
    filmy = o.kosze_windows([str(d)], "filmy", "zoom")
    assert len(filmy) == 1 and filmy[0]["oryginal"] == oryg and filmy[0]["rozmiar"] == 5
    assert o.przywroc(filmy[0], {"kosze": [str(tmp_path / "inny")]})["blad"]  # spoza znanych koszy — nie
    w = o.przywroc(filmy[0], {"kosze": o._kosze([str(d)])})
    assert w["ok"] and open(oryg, "rb").read() == b"12345"
    assert not (k / "$IABC123.mp4").exists() and not (k / "$RABC123.mp4").exists()
    with open(oryg, "wb") as f:  # zajęte miejsce → „(odzyskane)”
        f.write(b"nowy")
    a = [x for x in o.kosze_windows([str(d)], "zdjecia", "a.jpg")][0]
    (tmp_path / "a.jpg").write_bytes(b"zajete")
    assert o.przywroc(a, {"kosze": o._kosze([str(d)])})["sciezka"].endswith("a (odzyskane).jpg")


def test_kopia_zapasowa_pliki_usuniete_z_biblioteki(tmp_path):
    bib, kop = tmp_path / "Bib", tmp_path / "Kopia"
    for x in (bib / "2020", kop / "2020", kop / "Odłożone"):
        x.mkdir(parents=True)
    (bib / "2020" / "jest.jpg").write_bytes(b"1")
    (kop / "2020" / "jest.jpg").write_bytes(b"1")
    (kop / "2020" / "usuniete.jpg").write_bytes(b"22")
    (kop / "2020" / "film.mp4").write_bytes(b"333")
    (kop / "Odłożone" / "x.jpg").write_bytes(b"4")
    w = o.z_kopii(str(bib), str(kop), "zdjecia", "")
    assert [x["nazwa"] for x in w["pliki"]] == ["usuniete.jpg"]
    assert len(o.z_kopii(str(bib), str(kop), "wszystko", "")["pliki"]) == 2
    r = o.przywroc(w["pliki"][0], {"kopia": str(kop)})
    assert r["ok"] and (bib / "2020" / "usuniete.jpg").read_bytes() == b"22" and (kop / "2020" / "usuniete.jpg").exists()


def test_postep_i_wyniki_z_folderu_winfr(tmp_path):
    cel = tmp_path / "Odzyskane"
    rec = cel / "Recovery_20261015_101500" / "Users" / "Ja" / "Downloads"
    rec.mkdir(parents=True)
    (rec / "zoom_0.mp4").write_bytes(b"0" * 5000)
    (rec / "zdj.jpg").write_bytes(b"0" * 20)
    (cel / "Recovery_20261015_101500" / "RecoveryLog.txt").write_text("log")
    (cel / o.DZIENNIK).write_bytes("Pass 1: Scanning disk: 45%\rPass 1: Scanning disk: 87%\r\n".encode("utf-16"))
    z = {"cel": str(cel), "start": time.time() - 10, "zrodlo": "C:\\"}
    p = o.postep(z)
    assert p["procent"] == 87 and not p["zakonczone"] and p["znalezione"] == 2 and "87%" in p["komunikat"]
    (cel / o.KONIEC).write_text("0 ")
    assert o.postep(z)["zakonczone"] and o.postep(z)["kod"] == 0
    w = o.wyniki(z, "wszystko", "", 0)
    assert [x["nazwa"] for x in w["pliki"]] == ["zoom_0.mp4", "zdj.jpg"]
    assert w["pliki"][0]["gdzie"] == os.path.join("Users", "Ja", "Downloads")
    assert o.wyniki(z, "wszystko", "", 1)["razem"] == 1  # ≥ 1 KB
    assert o.w_wynikach(z, str(rec / "zdj.jpg")) and not o.w_wynikach(z, str(tmp_path / "inny.jpg"))
    stary = {"cel": str(cel), "start": time.time() + 3600}  # folder Recovery_ sprzed tego odzyskiwania — pomijany
    assert o.wyniki(stary)["razem"] == 0
