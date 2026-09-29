"""Wykrywanie dokumentów po tekście i grupowanie podobnych bez łańcuchów (zgłoszenia z prawdziwych zdjęć)."""
import random

import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from katalogator import analiza, duplikaty, skaner

SLOWA = "faktura paragon fiskalny suma ptu razem kwota netto brutto data sprzedaży nabywca nip płatność karta".split()


def _tekst(d, x0, y0, x1, y1, rozm, odstep, rnd):
    f = ImageFont.load_default(size=rozm)
    y = y0
    while y < y1 - rozm:
        x = x0
        while True:
            w = rnd.choice(SLOWA)
            dl = d.textlength(w + " ", font=f)
            if x + dl > x1:
                break
            d.text((x, y), w, fill=(25, 25, 30), font=f)
            x += dl
        y += odstep


def kartka(obrot=0, cien=False, W=1500, H=2000):
    rnd = random.Random(1)
    im = Image.new("RGB", (W, H), (120, 90, 60))
    k = Image.new("RGB", (int(W * .8), int(H * .8)), (245, 243, 236))
    _tekst(ImageDraw.Draw(k), 60, 75, k.width - 60, k.height - 75, 24, 39, rnd)
    k = k.rotate(obrot, expand=True, fillcolor=(120, 90, 60))
    im.paste(k, ((W - k.width) // 2, (H - k.height) // 2))
    if cien:
        m = Image.linear_gradient("L").resize((W, H)).point(lambda v: int(v * .5))
        im = Image.composite(Image.new("RGB", (W, H)), im, m)
    return im


def paragon():
    rnd = random.Random(2)
    im = Image.new("RGB", (1500, 2000), (70, 70, 80))
    k = Image.new("RGB", (550, 1850), (250, 250, 247))
    _tekst(ImageDraw.Draw(k), 30, 40, 520, 1800, 20, 31, rnd)
    im.paste(k.rotate(3, expand=True, fillcolor=(70, 70, 80)), (450, 50))
    return im


def snieg(z):
    r = random.Random(z)
    im = Image.new("RGB", (2016, 908), (235, 238, 242))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 2016, 350), fill=(205, 210, 218))
    for _ in range(450):
        x, y = r.randint(0, 2016), r.randint(300, 550)
        d.line((x, y, x + r.randint(-30, 30), y + r.randint(-40, 10)), fill=(45, 50, 45), width=r.randint(1, 3))
    d.rectangle((950, 450, 1450, 650), fill=(215, 180, 60))
    return im.filter(ImageFilter.GaussianBlur(1))


def osoba():
    im = Image.new("RGB", (908, 2016), (232, 230, 226))
    d = ImageDraw.Draw(im)
    d.rectangle((650, 0, 908, 2016), fill=(210, 215, 222))
    d.ellipse((350, 250, 525, 450), fill=(200, 160, 130))
    d.rectangle((280, 450, 600, 1250), fill=(25, 25, 30))
    d.rectangle((300, 1250, 400, 1950), fill=(20, 20, 25))
    d.rectangle((475, 1250, 575, 1950), fill=(20, 20, 25))
    return im


def niebo():
    g = Image.linear_gradient("L").resize((2016, 908))
    return Image.merge("RGB", [g.point(lambda v, a=a: int(150 + v * a)) for a in (.3, .35, .4)])


@pytest.mark.parametrize("nazwa,obraz", [
    ("kartka", lambda: kartka()), ("krzywa z cieniem", lambda: kartka(obrot=7, cien=True)),
    ("paragon", paragon), ("bokiem", lambda: kartka().rotate(90, expand=True)),
])
def test_dokumenty_wykryte(nazwa, obraz):
    assert analiza.ocena_tekstu(obraz()) >= analiza.PROG_PEWNY


@pytest.mark.parametrize("nazwa,obraz", [
    ("śnieg 1", lambda: snieg(1)), ("śnieg 2", lambda: snieg(2)), ("osoba przy ścianie", osoba), ("niebo", niebo),
])
def test_zdjecia_nie_sa_dokumentami(nazwa, obraz):
    assert analiza.ocena_tekstu(obraz()) < analiza.PROG_KANDYDAT


def na_ciemnym_stole():
    """Kartka zajmuje mały kawałek kadru, reszta to ciemny blat — etap 1 nie może jej zgubić."""
    im = Image.new("RGB", (4000, 3000), (55, 50, 45))
    k = kartka(W=1200, H=1600)
    im.paste(k.crop((120, 160, 1080, 1440)), (1500, 900))
    return im


def zaluzje():
    im = Image.new("RGB", (4000, 3000), (200, 200, 205))
    d = ImageDraw.Draw(im)
    for y in range(0, 3000, 40):
        d.rectangle((0, y, 4000, y + 8), fill=(90, 90, 95))
    return im.filter(ImageFilter.GaussianBlur(1.5))


def kratki():
    """Obudowa z kratkami wentylacyjnymi (jak spód dysku) — regularne, ale to nie tekst."""
    im = Image.new("RGB", (1848, 4000), (195, 196, 200))
    d = ImageDraw.Draw(im)
    for y in range(100, 3900, 110):
        for x in (150, 1050):
            d.rounded_rectangle((x, y, x + 650, y + 55), 20, fill=(40, 40, 45))
    return im.filter(ImageFilter.GaussianBlur(2))


def okna_budynku():
    im = Image.new("RGB", (4000, 3000), (215, 205, 185))
    d = ImageDraw.Draw(im)
    for i in range(14):
        for j in range(12):
            d.rectangle((200 + j * 310, 150 + i * 200, 300 + j * 310, 260 + i * 200), fill=(60, 60, 70))
    return im


def test_kartka_na_ciemnym_stole_przechodzi_oba_etapy():
    im = na_ciemnym_stole()
    assert analiza.ocena_dokumentu(im) >= analiza.PROG_WSTEPNY
    assert analiza.ocena_tekstu(im) >= analiza.PROG_KANDYDAT


@pytest.mark.parametrize("nazwa,obraz", [("żaluzje", zaluzje), ("kratki", kratki), ("okna budynku", okna_budynku)])
def test_regularne_wzory_to_nie_tekst(nazwa, obraz):
    assert analiza.ocena_tekstu(obraz()) < analiza.PROG_KANDYDAT


def _krajobraz(z, W=1600, H=720):
    """Niebo + góry — podobny układ, różna treść (jak zgłoszona błędna grupa)."""
    r = random.Random(z)
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    gora = (r.randint(60, 200), r.randint(80, 200), r.randint(120, 255))
    for y in range(H):
        t = y / H
        d.line((0, y, W, y), fill=tuple(int(c * (1 - t) + 40 * t) for c in gora))
    pkt = [(0, H)] + [(x, int(H * (0.45 + 0.25 * r.random()))) for x in range(0, W + 1, W // 8)] + [(W, H)]
    d.polygon(pkt, fill=(r.randint(10, 80), r.randint(40, 110), r.randint(10, 80)))
    for _ in range(25):
        x, y, s = r.randint(0, W), r.randint(0, H), r.randint(10, 90)
        d.ellipse((x, y, x + s, y + s), fill=(r.randint(0, 255), r.randint(0, 255), r.randint(0, 255)))
    return im


def test_podobne_bez_lancuchow(tmp_path):
    k = tmp_path / "dysk"
    k.mkdir()
    for i in range(8):  # różne krajobrazy
        _krajobraz(100 + i).save(k / f"krajobraz_{i}.jpg", quality=88)
    seria = _krajobraz(7)
    seria.save(k / "seria_1.jpg", quality=90)
    seria.transform(seria.size, Image.Transform.AFFINE, (1, 0, 8, 0, 1, 3)).save(k / "seria_2.jpg", quality=90)
    seria.resize((800, 360)).save(k / "seria_whatsapp.jpg", quality=55)
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    duplikaty.przygotuj(db)
    analiza.analizuj(db)
    grupy = analiza.grupy_podobnych(db)
    nazwy = [sorted(w["wzgledna"] for w in g) for g in grupy]
    assert ["seria_1.jpg", "seria_2.jpg", "seria_whatsapp.jpg"] in nazwy
    assert all(len(g) <= 3 for g in grupy), nazwy  # różne krajobrazy nie sklejają się w jedną grupę


def test_stara_analiza_jest_przeliczana(tmp_path):
    k = tmp_path / "dysk"
    k.mkdir()
    kartka().save(k / "umowa.jpg", quality=85)
    snieg(1).save(k / "snieg.jpg", quality=85)
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    duplikaty.przygotuj(db)
    analiza.analizuj(db)
    db.execute("UPDATE analiza SET podpis=NULL, tekst=NULL")  # jak po wersji 1.2.0
    db.commit()
    analiza.analizuj(db)
    kand = [c["wzgledna"] for c in analiza.kandydaci_dokumentow(db)]
    assert kand == ["umowa.jpg"]
    assert db.execute("SELECT COUNT(*) FROM analiza WHERE podpis IS NULL").fetchone()[0] == 0
