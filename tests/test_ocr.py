"""📄 OCR dokumentów: tekst potwierdza dokument, wzór bez liter go wyklucza, a tekst da się wyszukać."""
import random

import pytest
from PIL import Image, ImageDraw

from katalogator import analiza, galeria, ocr, skaner
from test_analiza import _dokument

pytestmark = pytest.mark.skipif(ocr.dostepne() is not None, reason="brak rapidocr / onnxruntime")


def _pasy(sciezka):
    """Jasne żaluzje: równe ciemne pasy — wyglądają jak wiersze tekstu, ale liter nie ma."""
    im = Image.new("RGB", (1400, 1800), (238, 236, 230))
    d = ImageDraw.Draw(im)
    for y in range(80, 1720, 40):
        for x in range(100, 1300, 64):
            d.rectangle((x, y, x + 44, y + 9), fill=(40, 40, 45))
    im.save(sciezka, quality=88)


def test_ocr_czyta_polskie_znaki():
    import glob
    import os
    from PIL import ImageFont
    czcionki = sorted(glob.glob("/usr/share/fonts/**/DejaVuSans.ttf", recursive=True)) + \
        [p for p in (os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "arial.ttf"),) if os.path.exists(p)]
    if not czcionki:
        pytest.skip("brak czcionki z polskimi znakami")
    im = Image.new("RGB", (1200, 500), "white")
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(czcionki[0], 34)
    d.text((40, 60), "FAKTURA VAT nr 12/2024", fill="black", font=f)
    d.text((40, 160), "Zakład Usług Różnych, Łódź", fill="black", font=f)
    d.text((40, 260), "Razem do zapłaty: 123,45 zł", fill="black", font=f)
    w = ocr.czytaj_obraz(im)
    assert "FAKTURA" in w["tekst"] and "zapłaty" in w["tekst"] and "Łódź" in w["tekst"]
    assert w["znaki"] >= 50


def test_ocr_w_analizie_dokumentow(tmp_path):
    random.seed(3)
    k = tmp_path / "zdjecia"
    k.mkdir()
    _dokument(k / "skan.jpg")
    _pasy(k / "zaluzje.jpg")
    db = skaner.otworz_baze(tmp_path / "k.db")
    skaner.skanuj(str(k), db, wypisz=lambda *_: None)
    analiza.analizuj(db)
    a = {r["sciezka"].rsplit("/", 1)[-1].rsplit("\\", 1)[-1]: dict(r) for r in
         db.execute("SELECT sciezka, tekst, ocr_znaki, ocr_tekst FROM analiza")}
    assert a["skan.jpg"]["ocr_znaki"] >= 150 and "faktura" in a["skan.jpg"]["ocr_tekst"]
    kand = {d["wzgledna"]: d for d in analiza.kandydaci_dokumentow(db)}
    assert "skan.jpg" in kand and kand["skan.jpg"]["ocena"] >= analiza.PROG_PEWNY and kand["skan.jpg"]["ocr"]
    # druga analiza niczego nie czyta ponownie
    znaki = a["skan.jpg"]["ocr_znaki"]
    analiza.analizuj(db)
    assert db.execute("SELECT ocr_znaki FROM analiza WHERE sciezka LIKE '%skan.jpg'").fetchone()[0] == znaki
    # 🔍 wyszukiwanie po odczytanym tekście (Biblioteka projektu = ta sama baza)
    g = galeria.Galeria(tmp_path / "k.db")
    assert [p["nazwa"] for p in g.szukaj("nabywca")["pliki"]] == ["skan.jpg"]
    assert g.szukaj("pesel")["razem"] == 0
    # wzór „jak wiersze tekstu” (pasy, kafelki), na którym OCR nie znalazł liter — to nie dokument
    db.execute("UPDATE analiza SET ocr_znaki=3 WHERE sciezka LIKE '%skan.jpg'")
    db.commit()
    assert "skan.jpg" not in {d["wzgledna"] for d in analiza.kandydaci_dokumentow(db)}
    db.execute("UPDATE analiza SET ocr_znaki=-1 WHERE sciezka LIKE '%skan.jpg'")  # nie dało się przeczytać:
    db.commit()                                                                    # zostaje ocena z wyglądu
    assert "skan.jpg" in {d["wzgledna"] for d in analiza.kandydaci_dokumentow(db)}


def test_tekst_z_projektu_widoczny_w_przegladarce(tmp_path):
    """OCR w projekcie trafia do wspólnego indeksu — Przeglądarka (osobna baza, bez analizy) też go znajduje,
    a drugi projekt nie czyta tego samego pliku jeszcze raz."""
    from katalogator import indeks
    random.seed(5)
    k = tmp_path / "zdjecia"
    k.mkdir()
    _dokument(k / "umowa.jpg")
    indeks.ustaw(tmp_path / "indeks.db")
    try:
        projekt = skaner.otworz_baze(tmp_path / "projekt.db")
        skaner.skanuj(str(k), projekt, wypisz=lambda *_: None)
        analiza.analizuj(projekt)
        prz = skaner.otworz_baze(tmp_path / "przegladarka.db")
        skaner.skanuj(str(k), prz, wypisz=lambda *_: None)
        g = galeria.Galeria(tmp_path / "przegladarka.db")
        assert [p["nazwa"] for p in g.szukaj("nabywca")["pliki"]] == ["umowa.jpg"]
        drugi = skaner.otworz_baze(tmp_path / "drugi.db")
        skaner.skanuj(str(k), drugi, wypisz=lambda *_: None)
        czytane = []
        orig = ocr.czytaj
        ocr.czytaj = lambda sc: czytane.append(sc) or orig(sc)
        try:
            analiza.analizuj(drugi)
        finally:
            ocr.czytaj = orig
        assert czytane == [] and drugi.execute("SELECT ocr_znaki FROM analiza").fetchone()[0] > 100
    finally:
        indeks.ustaw(None)
