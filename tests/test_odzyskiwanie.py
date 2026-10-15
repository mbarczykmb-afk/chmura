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


def test_wybrane_formaty():
    assert o.rozszerzenia(["MP4", ".mov", "*.mts", "zly/format", "mp4"]) == [".mp4", ".mov", ".mts"]
    assert o.rozszerzenia("filmy") == o.TYPY["filmy"] and o.rozszerzenia("nieznany") == []
    assert ".mp3" in o.TYPY["muzyka"] and ".zip" in o.TYPY["archiwa"]
    assert o.wzorce("\\Users\\Ja\\Videos\\", [".mp4", ".mts"], "") == ["\\Users\\Ja\\Videos\\*.mp4", "\\Users\\Ja\\Videos\\*.mts"]
    assert o.pasuje("klip.MTS", [".mts"], "") and not o.pasuje("klip.mp4", [".mts"], "")
    assert o.pasuje("utwor.flac", "muzyka", "") and not o.pasuje("zdj.jpg", "muzyka", "")
    assert o.rodzaj_pliku("a.mp3") == "muzyka"


def test_dokad_przywracac(tmp_path):
    assert o.folder_wynikow("E:\\") == "E:\\Odzyskane_Katalogator"
    assert o.folder_wynikow("E:") == "E:\\Odzyskane_Katalogator"
    assert o.folder_wynikow("E:\\Moje\\Odzysk") == "E:\\Moje\\Odzysk"
    d = tmp_path / "dysk"
    k = d / "$Recycle.Bin" / "S-1"
    k.mkdir(parents=True)
    (k / "$I9.mp4").write_bytes(_i(str(tmp_path / "Pobrane" / "film.mp4"), 3))
    (k / "$R9.mp4").write_bytes(b"abc")
    cel = tmp_path / "Wybrany"
    el = o.kosze_windows([str(d)], "filmy", "")[0]
    assert o.przywroc(el, {"kosze": o._kosze([str(d)])}, str(tmp_path / "brak"))["blad"]
    w = o.przywroc(el, {"kosze": o._kosze([str(d)])}, str(cel) if cel.mkdir() is None else "")
    assert w["ok"] and (cel / "film.mp4").read_bytes() == b"abc" and not (tmp_path / "Pobrane").exists()


def test_skrypt_z_dyskiem_sieciowym():
    a = o.polecenie("winfr.exe", "C:", "Z:\\Odzysk", True, ["*100%*.mp4"])
    s = o.skrypt_cmd(a[:2], a[3:], "Z:\\Odzysk", "\\\\nas\\Public")
    assert 'net use Z: "\\\\nas\\Public"' in s and 'set "CEL=\\\\nas\\Public\\Odzysk"' in s
    assert 'winfr.exe C: "%CEL%" /extensive /n *100%%*.mp4 /a > "%LOG%" 2>&1' in s  # % w filtrze podwojony
    assert 'echo Start %date% %time% > "%INF%"' in s  # komunikaty skryptu osobno od dziennika winfr
    assert 'set "LOG=Z:\\Odzysk\\winfr.log"' in s  # bez folderu roboczego — dziennik obok wyników
    r = o.skrypt_cmd(a[:2], a[3:], "Z:\\Odzysk", "\\\\nas\\Public", "C:\\Dane\\odzysk")
    assert 'set "LOG=C:\\Dane\\odzysk\\winfr.log"' in r and "BLAD: brak dostepu" in r
    lok = o.skrypt_cmd(a[:2], a[3:], "E:\\Odzyskane_Katalogator")
    assert "net use" not in lok and 'set "CEL=E:\\Odzyskane_Katalogator"' in lok
    assert o._unc("Z:\\Odzysk\\.x.cmd", "\\\\nas\\Public\\") == "\\\\nas\\Public\\Odzysk\\.x.cmd"
    assert o._unc("E:\\a", "") == "E:\\a"


def test_odzyskiwanie_ktore_nie_ruszylo(tmp_path):
    rob = tmp_path / "odzysk"
    rob.mkdir()
    z = {"cel": str(tmp_path / "wyniki"), "robocze": str(rob), "start": time.time() - 120}
    assert o.postep(z)["nie_ruszylo"]
    (rob / o.DZIENNIK).write_text("Start 15.10.2026\nZapis do: Y:\\Odzyskane")
    p = o.postep(z)
    assert not p["nie_ruszylo"] and not p["zakonczone"] and "Zapis do" in p["komunikat"]
    (rob / o.KONIEC).write_text("3 ")
    assert o.postep(z)["kod"] == 3


def test_dziennik_winfr_utf16_i_podpowiedz(tmp_path):
    rob = tmp_path / "r"
    rob.mkdir()
    (rob / o.INFO).write_text("Start 15.10.2026\nZapis do: Y:\\Odzyskane\n")
    (rob / o.DZIENNIK).write_bytes("Windows File Recovery\r\nFailed to create destination folder, Error 0x80070356: "
                                   "Unknown error 0x80070356\r\n".encode("utf-16"))
    (rob / o.KONIEC).write_text("1")
    p = o.postep({"cel": str(tmp_path / "w"), "robocze": str(rob), "start": time.time()})
    assert p["kod"] == 1 and "folderu na odzyskane" in p["wskazowka"]
    assert "Start 15.10.2026" in p["dziennik"] and "Failed to create destination folder" in p["dziennik"]


def test_bezpieczna_sciezka_docelowa(monkeypatch):
    assert o.bezpieczna("D:\\Odzyskane_Katalogator") and o.bezpieczna(o.folder_wynikow("D:\\"))
    assert not o.bezpieczna("D:\\Odzysk 2026") and not o.bezpieczna("E:\\Zdjęcia")
    monkeypatch.setattr(o, "winfr", lambda: "winfr.exe")
    assert "spacje" in o.uruchom("C:", "D:\\Moje odzyskane", "", "wszystko", "", True)["blad"]


def test_czytelny_postep_winfr():
    t = o._czysc("Pass 1: Scanning and processing disk\r\nScanning disk: 00%\b\b\b01%\b\b\b97%\r\n\x00")
    assert t == "Pass 1: Scanning and processing disk\nScanning disk: 97%"


def test_stan_odzyskanych_plikow(tmp_path):
    cel = tmp_path / "Odzysk"
    rec = cel / "Recovery_20261015_190000"
    rec.mkdir(parents=True)
    (rec / "pusty.mp4").write_bytes(b"\0" * 300000)  # SSD po TRIM: same zera
    (rec / "zly.mp4").write_bytes(b"\x01\x02" * 1000)
    (rec / "dobry.mp4").write_bytes(b"\0\0\0\x10ftypmp42\0\0\0\0" + b"\0\0\0\x10moov" + b"\1" * 8 + b"\0\0\0\x10mdat" + b"\1" * 8)
    (rec / "bez.mp4").write_bytes(b"\0\0\0\x10ftypmp42\0\0\0\0" + (1000).to_bytes(4, "big") + b"mdat" + b"\1" * 992)
    (rec / "kod.d.mts").write_bytes(b"export declare const x: number;\n" * 20)
    (rec / "zdj.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\1" * 100)
    assert o.stan_pliku(str(rec / "pusty.mp4")) == "pusty"
    assert o.stan_pliku(str(rec / "zly.mp4")) == "uszkodzony"
    assert o.stan_pliku(str(rec / "dobry.mp4")) == "ok" and o.stan_pliku(str(rec / "zdj.jpg")) == "ok"
    assert o.stan_pliku(str(rec / "bez.mp4")) == "bez_indeksu" and o.stan_pliku(str(rec / "kod.d.mts")) == "tekst"
    w = o.wyniki({"cel": str(cel), "start": time.time() - 10})
    assert w["stany"] == {"ok": 2, "bez_indeksu": 1, "uszkodzony": 1, "tekst": 1, "pusty": 1}
    assert [x["nazwa"] for x in w["pliki"]][-1] == "pusty.mp4" and w["pliki"][0]["stan"] == "ok"
