import io
import random

import pytest
from PIL import Image, ImageDraw, ImageFilter

from katalogator import analiza, duplikaty, skaner


def _dokument(sciezka, szum=0):
    """Kartka z tekstem (litery, nie paski) sfotografowana na stole."""
    from PIL import ImageFont
    slowa = "faktura paragon suma razem kwota netto brutto data nabywca umowa strona termin".split()
    im = Image.new("RGB", (1400, 1800), (120, 95, 70))
    k = Image.new("RGB", (1200, 1600), (245, 243, 238))
    d = ImageDraw.Draw(k)
    f = ImageFont.load_default(size=26)
    for y in range(120, 1500, 42):
        x = 100
        while True:
            w = random.choice(slowa)
            dl = d.textlength(w + " ", font=f)
            if x + dl > 1100:
                break
            d.text((x, y), w, fill=(30, 30, 35), font=f)
            x += dl
    im.paste(k, (100, 100))
    im.save(sciezka, quality=88)


def _zdjecie(sciezka, ziarno=1, rozmiar=(1600, 1200), rozmyj=0, jakosc=90):
    rnd = random.Random(ziarno)
    im = Image.new("RGB", rozmiar)
    d = ImageDraw.Draw(im)
    for y in range(rozmiar[1]):  # niebo -> trawa
        t = y / rozmiar[1]
        d.line((0, y, rozmiar[0], y), fill=(int(80 + 60 * t), int(140 + 60 * t), int(220 - 170 * t)))
    for _ in range(40):
        x, y, r = rnd.randint(0, rozmiar[0]), rnd.randint(0, rozmiar[1]), rnd.randint(20, 160)
        d.ellipse((x, y, x + r, y + r), fill=(rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255)))
    if rozmyj:
        im = im.filter(ImageFilter.GaussianBlur(rozmyj))
    im.save(sciezka, quality=jakosc)
    return im


def _z_miniatura_exif(sciezka, im):
    """Zapis JPEG z miniaturą w EXIF (jak w aparatach) — sklejamy APP1 ręcznie."""
    mini = im.copy()
    mini.thumbnail((160, 120))
    b = io.BytesIO()
    mini.save(b, "JPEG", quality=80)
    thumb = b.getvalue()
    # minimalny TIFF z IFD0 (pusty) i IFD1 wskazującym miniaturę
    import struct
    ifd1_off = 8 + 2 + 4
    tiff = b"MM\x00\x2a" + struct.pack(">I", 8) + struct.pack(">H", 0) + struct.pack(">I", ifd1_off)
    wpisy = [(0x0201, 4, 1, 0), (0x0202, 4, 1, len(thumb))]
    ifd1 = struct.pack(">H", len(wpisy))
    dane_off = ifd1_off + 2 + 12 * len(wpisy) + 4
    for tag, typ, n, wart in wpisy:
        ifd1 += struct.pack(">HHII", tag, typ, n, dane_off if tag == 0x0201 else wart)
    ifd1 += struct.pack(">I", 0)
    app1 = b"Exif\x00\x00" + tiff + ifd1 + thumb
    glowny = io.BytesIO()
    im.save(glowny, "JPEG", quality=90)
    g = glowny.getvalue()
    with open(sciezka, "wb") as f:
        f.write(g[:2] + b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1 + g[2:])


def test_ocena_dokumentu_rozroznia(tmp_path):
    random.seed(3)
    _dokument(tmp_path / "paragon.jpg")
    _zdjecie(tmp_path / "las.jpg")
    doc = analiza.ocena_dokumentu(analiza.miniatura(str(tmp_path / "paragon.jpg"))[0])
    fot = analiza.ocena_dokumentu(analiza.miniatura(str(tmp_path / "las.jpg"))[0])
    assert doc >= analiza.PROG_PEWNY and fot < analiza.PROG_KANDYDAT, (doc, fot)


def test_miniatura_z_exif_bez_czytania_calosci(tmp_path, monkeypatch):
    im = _zdjecie(tmp_path / "tmp.jpg", rozmiar=(4000, 3000))
    p = tmp_path / "aparat.jpg"
    _z_miniatura_exif(p, im)
    wolania = []
    orig = Image.open
    monkeypatch.setattr(Image, "open", lambda f, *a, **k: (wolania.append(f), orig(f, *a, **k))[1])
    mini, rozm = analiza.miniatura(str(p))
    assert rozm == (4000, 3000) and max(mini.size) == 160
    assert not any(isinstance(w, str) for w in wolania)  # pełnego pliku nie otwierano


def test_podobne_i_nieostre(tmp_path):
    k = tmp_path / "dysk"
    (k / "WhatsApp").mkdir(parents=True)
    oryg = _zdjecie(k / "IMG_1.jpg", ziarno=1)
    oryg.resize((800, 600)).save(k / "WhatsApp" / "IMG-WA0001.jpg", quality=55)  # przesłane dalej
    _zdjecie(k / "IMG_2.jpg", ziarno=2)
    _zdjecie(k / "IMG_3_rozmyte.jpg", ziarno=3, rozmyj=8)
    random.seed(1)
    _dokument(k / "umowa.jpg")
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    duplikaty.przygotuj(db)
    pod = analiza.analizuj(db)
    assert pod["przeanalizowane"] == 5
    grupy = analiza.grupy_podobnych(db)
    assert len(grupy) == 1
    nazwy = [w["wzgledna"].replace("\\", "/") for w in grupy[0]]
    assert nazwy[0] == "IMG_1.jpg" and "WhatsApp/IMG-WA0001.jpg" in nazwy  # większa rozdzielczość pierwsza
    assert analiza.najmniej_ostre(db, 1)[0]["wzgledna"] == "IMG_3_rozmyte.jpg"
    kand = analiza.kandydaci_dokumentow(db)
    assert [c["wzgledna"] for c in kand] == ["umowa.jpg"] and kand[0]["zaznacz"]
    analiza.zapisz_decyzje(db, [kand[0]["id"]], [])
    assert analiza.dokumenty_potwierdzone(db) == {str(k / "umowa.jpg")}
    assert analiza.kandydaci_dokumentow(db, tylko_nowe=True) == []
    # druga analiza nic nie liczy
    etapy = []
    analiza.analizuj(db, postep=lambda e, z, n, b: etapy.append(n))
    assert max(etapy) == 0


def test_odloz_podobne_i_cofnij(tmp_path):
    k = tmp_path / "dysk"
    k.mkdir()
    _zdjecie(k / "a.jpg", ziarno=1).resize((800, 600)).save(k / "b.jpg")
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    duplikaty.przygotuj(db)
    ids = {r["wzgledna"]: r["rowid"] for r in db.execute("SELECT rowid, wzgledna FROM pliki")}
    w = duplikaty.odloz(db, [ids["b.jpg"]], "podobne")
    assert w["przeniesione"] == 1 and (k / "Odłożone" / "Podobne" / "b.jpg").exists()
    assert duplikaty.ostatnia_partia(db)["typ"] == "podobne"
    assert duplikaty.cofnij(db)["przywrocone"] == 1 and (k / "b.jpg").exists()


def test_podobne_kopie_w_wielu_folderach_to_jedno_zdjecie(tmp_path):
    """Ta sama seria w kilku folderach (kopia zapasowa, zapisana na nowo) — jedna grupa, kopie oznaczone,
    a „⚡ odłóż same kopie” zostawia po jednym egzemplarzu każdego zdjęcia z serii."""
    import os
    from katalogator import aplikacja
    k = tmp_path / "dysk"
    for f in ("Wakacje", "Kopia zapasowa", "Stary telefon"):
        (k / f).mkdir(parents=True)
    a = _zdjecie(k / "Wakacje" / "IMG_1.jpg", ziarno=1)
    a.filter(ImageFilter.GaussianBlur(1.5)).save(k / "Wakacje" / "IMG_2.jpg", quality=90)  # drugie ujęcie serii
    for f, q in (("Kopia zapasowa", 70), ("Stary telefon", 60)):
        for n in ("IMG_1.jpg", "IMG_2.jpg"):
            Image.open(k / "Wakacje" / n).save(k / f / (n.replace(".jpg", " (1).jpg") if q == 60 else n), quality=q)
    for p in k.rglob("*.jpg"):  # ta sama data zrobienia dla kopii
        os.utime(p, (1_600_000_000 + int(p.name[4]), 1_600_000_000 + int(p.name[4])))
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    duplikaty.przygotuj(db)
    analiza.analizuj(db)
    grupy = analiza.grupy_podobnych(db)
    assert len(grupy) == 1 and len(grupy[0]) == 6
    assert sum(w["kopia"] for w in grupy[0]) == 4 and not grupy[0][0]["kopia"]
    ids = aplikacja._podobne_hurtem(db, "kopie")
    assert len(ids) == 4
    zostaja = [w for w in grupy[0] if w["id"] not in ids]
    assert sorted(analiza._rdzen_nazwy(w["sciezka"]) for w in zostaja) == ["img_1", "img_2"]
    assert len(aplikacja._podobne_hurtem(db, "najlepsze")) == 5
