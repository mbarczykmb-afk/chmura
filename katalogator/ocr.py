"""📄 Czytanie tekstu ze zdjęć (OCR) — RapidOCR z modelami PaddleOCR (PP-OCRv6, ONNX), w całości na komputerze.

Modele (ok. 31 MB) są w paczce rapidocr, nic nie jest pobierane. Polski jest w zestawie łacińskim modeli.
Czytamy tylko zdjęcia, które wstępna analiza uznała za możliwe dokumenty — OCR całej biblioteki trwałby godzinami.
Liczba pewnie odczytanych znaków podnosi albo obniża ocenę „dokument” (analiza.ocena_z_ocr), a sam tekst
można potem wyszukać (np. „faktura”, „PESEL”).
"""
from __future__ import annotations

import logging
import threading

from PIL import Image, ImageOps

LOG = logging.getLogger("katalogator.ocr")

BOK = 1600          # dłuższy bok zdjęcia przed czytaniem: kartka A4 nadal czytelna, a czas ~1 s
PEWNOSC = 0.6       # wiersze z niższą pewnością pomijamy (wzory, liście, kafelki „udające” litery)
MAKS_TEKSTU = 4000  # tyle znaków tekstu zapisujemy do wyszukiwania

_SILNIK = None
_BLOKADA = threading.Lock()


def dostepne() -> str | None:
    """None, gdy można czytać tekst; inaczej powód."""
    try:
        import onnxruntime  # noqa: F401
        import rapidocr  # noqa: F401
    except ImportError:
        return "Brak modułu OCR (rapidocr) — zainstaluj nową wersję Katalogatora."
    return None


def _silnik():
    global _SILNIK
    if _SILNIK is None:
        from rapidocr import RapidOCR
        # bez klasyfikatora obrotu wierszy: dokumenty są w zdjęciach już obrócone (EXIF), a to ~15% czasu mniej
        _SILNIK = RapidOCR(params={"Global.log_level": "error", "Global.use_cls": False})
    return _SILNIK


def _obraz(sciezka: str) -> Image.Image:
    with Image.open(sciezka) as im:
        im.draft("RGB", (BOK, BOK))  # JPEG: dekodowanie od razu w zmniejszonej skali
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((BOK, BOK))
        return im


def czytaj_obraz(im: Image.Image) -> dict:
    """{"tekst": wiersze rozdzielone \\n, "znaki": liczba liter i cyfr w pewnych wierszach}."""
    with _BLOKADA:  # jeden silnik, jedno czytanie naraz (onnxruntime i tak używa wszystkich rdzeni)
        w = _silnik()(im)
    wiersze = [t for t, s in zip(w.txts or (), w.scores or ()) if s >= PEWNOSC and t.strip()]
    return {"tekst": "\n".join(wiersze)[:MAKS_TEKSTU], "znaki": sum(c.isalnum() for t in wiersze for c in t)}


def czytaj(sciezka: str) -> dict:
    return czytaj_obraz(_obraz(sciezka))
