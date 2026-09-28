import os
import threading

import pytest

from katalogator import duplikaty, skaner


def _pliki(tmp_path):
    k = tmp_path / "dysk"
    (k / "Zdjecia" / "2020").mkdir(parents=True)
    (k / "Pobrane").mkdir()
    (k / "Kopia zapasowa").mkdir()
    duze = os.urandom(3 * duplikaty.BLOK + 123)
    (k / "Zdjecia" / "2020" / "wakacje.jpg").write_bytes(duze)
    (k / "Pobrane" / "wakacje.jpg").write_bytes(duze)
    (k / "Kopia zapasowa" / "wakacje (1).jpg").write_bytes(duze)
    # ten sam rozmiar i te same 1 MB z początku i końca, ale inny środek -> NIE duplikat
    inny = bytearray(duze); inny[len(duze) // 2] ^= 0xFF
    (k / "Zdjecia" / "podobny.jpg").write_bytes(bytes(inny))
    (k / "a.txt").write_text("to samo")
    (k / "b.txt").write_text("to samo")
    (k / "c.txt").write_text("inne!!!")  # ten sam rozmiar, inna treść
    (k / "d.txt").write_text("krótki")  # inny rozmiar -> bez odcisku
    return k


def _db(tmp_path, k):
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    return db


def test_wykrywa_tylko_identyczne(tmp_path):
    k = _pliki(tmp_path)
    db = _db(tmp_path, k)
    etapy = []
    w = duplikaty.szukaj(db, postep=lambda e, *a: etapy.append(e))
    assert w["grupy"] == 2 and w["nadmiar"] == 3
    assert "dokładne sprawdzanie" in etapy
    g = duplikaty.grupy(db)
    assert [x["n"] for x in g] == [3, 2]  # największa strata miejsca pierwsza
    # zostaje plik z porządnego folderu, nie z "Pobrane" / "Kopia zapasowa"
    zostaw = next(p for p in g[0]["pliki"] if p["id"] == g[0]["zostaw"])
    assert zostaw["wzgledna"].replace("\\", "/") == "Zdjecia/2020/wakacje.jpg"
    assert not any("podobny" in p["wzgledna"] for x in g for p in x["pliki"])


def test_drugie_wyszukiwanie_nie_czyta_plikow(tmp_path):
    k = _pliki(tmp_path)
    db = _db(tmp_path, k)
    duplikaty.szukaj(db)
    bajty = []
    duplikaty.szukaj(db, postep=lambda e, z, n, b: bajty.append(b))
    assert max(bajty) == 0


def test_miejsce_docelowe_wygrywa(tmp_path):
    k = _pliki(tmp_path)
    cel = tmp_path / "cel"; cel.mkdir()
    (cel / "x.txt").write_text("to samo")
    db = _db(tmp_path, k)
    skaner.skanuj(str(cel), db, wypisz=lambda *_: None)
    duplikaty.szukaj(db)
    g = [x for x in duplikaty.grupy(db, cele={str(cel)}) if x["rozmiar"] == 7][0]
    zostaw = next(p for p in g["pliki"] if p["id"] == g["zostaw"])
    assert zostaw["korzen"] == str(cel)


def test_przenies_i_cofnij(tmp_path):
    k = _pliki(tmp_path)
    db = _db(tmp_path, k)
    duplikaty.szukaj(db)
    g = duplikaty.grupy(db)[0]
    usun = [p["id"] for p in g["pliki"] if p["id"] != g["zostaw"]]
    w = duplikaty.przenies(db, [{"zostaw": g["zostaw"], "usun": usun}])
    assert w["przeniesione"] == 2 and not w["pominiete"]
    assert not (k / "Pobrane" / "wakacje.jpg").exists()
    assert (k / duplikaty.FOLDER_DUPLIKATOW / "Pobrane" / "wakacje.jpg").exists()
    assert (k / "Zdjecia" / "2020" / "wakacje.jpg").exists()
    assert duplikaty.podsumowanie(db)["nadmiar"] == 1
    # ponowny skan nie widzi odłożonych duplikatów
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    assert db.execute("SELECT COUNT(*) FROM pliki WHERE wzgledna LIKE '%Duplikaty%'").fetchone()[0] == 0

    c = duplikaty.cofnij(db)
    assert c["przywrocone"] == 2 and not c["bledy"]
    assert (k / "Pobrane" / "wakacje.jpg").exists()
    assert not (k / duplikaty.FOLDER_DUPLIKATOW).exists()
    assert duplikaty.ostatnia_partia(db) is None


def test_nie_przenosi_gdy_grupa_niezgodna(tmp_path):
    k = _pliki(tmp_path)
    db = _db(tmp_path, k)
    duplikaty.szukaj(db)
    ids = {r["wzgledna"].replace("\\", "/"): r["rowid"] for r in db.execute("SELECT rowid, wzgledna FROM pliki")}
    # a.txt i c.txt mają ten sam rozmiar, ale różną treść
    w = duplikaty.przenies(db, [{"zostaw": ids["a.txt"], "usun": [ids["c.txt"]]}])
    assert w["przeniesione"] == 0 and w["pominiete"]
    w = duplikaty.przenies(db, [{"zostaw": ids["a.txt"], "usun": [ids["d.txt"]]}])
    assert w["przeniesione"] == 0 and w["pominiete"]
    # zostaw == usun -> ignorowane
    w = duplikaty.przenies(db, [{"zostaw": ids["a.txt"], "usun": [ids["a.txt"]]}])
    assert w["przeniesione"] == 0
    assert (k / "c.txt").exists() and (k / "a.txt").exists() and (k / "d.txt").exists()


def test_zmieniony_plik_nie_jest_przenoszony(tmp_path):
    k = _pliki(tmp_path)
    db = _db(tmp_path, k)
    duplikaty.szukaj(db)
    g = [x for x in duplikaty.grupy(db) if x["rozmiar"] == 7][0]
    drugi = next(p for p in g["pliki"] if p["id"] != g["zostaw"])
    os.utime(drugi["sciezka"], (1, 1))
    w = duplikaty.przenies(db, [{"zostaw": g["zostaw"], "usun": [drugi["id"]]}])
    assert w["przeniesione"] == 0 and "Zmieniony" in w["pominiete"][0]


def test_przerwanie(tmp_path):
    k = _pliki(tmp_path)
    db = _db(tmp_path, k)
    ev = threading.Event(); ev.set()
    with pytest.raises(skaner.Przerwano):
        duplikaty.szukaj(db, przerwij=ev)


def test_oryginal_z_aparatu_wygrywa_z_whatsapp(tmp_path):
    k = tmp_path / "dysk"
    for f in ("Zdjęcia/2021 Wakacje", "WhatsApp Images", "Pobrane"):
        (k / f).mkdir(parents=True)
    dane = os.urandom(5000)
    for p in ("Zdjęcia/2021 Wakacje/IMG_20210710_120000.jpg", "WhatsApp Images/IMG-20210710-WA0003.jpg",
              "Pobrane/IMG_20210710_120000 (1).jpg"):
        (k / p).write_bytes(dane)
        os.utime(k / p, (1_600_000_000, 1_600_000_000))
    db = _db(tmp_path, k)
    duplikaty.szukaj(db)
    g = duplikaty.grupy(db)[0]
    zostaw = next(p for p in g["pliki"] if p["id"] == g["zostaw"])
    assert zostaw["wzgledna"].replace("\\", "/") == "Zdjęcia/2021 Wakacje/IMG_20210710_120000.jpg"
