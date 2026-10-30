"""📍 Rozpoznawanie miejsca ze zdjęcia (GeoCLIP, NeurIPS 2023) — ostatnia deska ratunku dla zdjęć bez GPS, których nie da się
dopasować do żadnego śladu. Daje przybliżenie (często poziom regionu lub miasta), więc zawsze trafia do przeglądu jako
propozycja do potwierdzenia, nigdy nie jest zapisywane samo.

Model jest przygotowany w CI (narzedzia/geoclip/zbuduj.py): koder obrazu CLIP ViT-L/14 + MLP GeoCLIP w ONNX (int8) i cechy
galerii 100 tys. miejsc. Program pobiera go z wydania na GitHubie dopiero przy pierwszym użyciu (ok. 400 MB) i sprawdza SHA-256.
Działa w całości lokalnie — zdjęcia nigdzie nie są wysyłane.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

LOG = logging.getLogger("katalogator.geoclip")

WYDANIE = "https://github.com/mbarczykmb-afk/chmura/releases/download/geoclip-model-1/"
PLIK_MODELU = "geoclip-obraz-int8.onnx"
PLIK_GALERII = "geoclip-galeria.npz"
# SHA-256 plików z wydania geoclip-model-1 (CI: fp32 = oryginał GeoCLIP, int8 — wieża Eiffla 0 km, Empire State 0,1 km)
SUMY: dict[str, str | None] = {PLIK_MODELU: "c12a40e15a83f8d3946fc02a6c2a4d2cef1e14511a5f83c3d0099057749d4369",
                               PLIK_GALERII: "ae3e5032fdec939834bd4343b87b5961d35f3d388f879b1ff68b2bba0756d779"}

_SREDNIA = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
_ODCHYL = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)

_stan = {"trwa": False, "zrobione": 0, "wszystkie": 0, "komunikat": "", "blad": ""}
_blokada = threading.Lock()
_model = None   # (sesja ONNX, Galeria) — ładowane raz


def przygotuj(zrodlo) -> np.ndarray:
    """Obraz → tensor (3, 224, 224) jak CLIPImageProcessor: krótszy bok 224 (bicubic), wycięcie środka, normalizacja CLIP."""
    with Image.open(zrodlo) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        w, h = im.size
        if w <= h:
            nw, nh = 224, int(224 * h / w)
        else:
            nw, nh = int(224 * w / h), 224
        im = im.resize((nw, nh), Image.BICUBIC)
        gora, lewo = (nh - 224) // 2, (nw - 224) // 2
        im = im.crop((lewo, gora, lewo + 224, gora + 224))
        x = np.asarray(im, dtype=np.float32) / 255.0
    x = (x - _SREDNIA) / _ODCHYL
    return np.ascontiguousarray(x.transpose(2, 0, 1), dtype=np.float32)


class Galeria:
    """100 tys. miejsc z cechami GeoCLIP; najlepsze(cecha, k) → [(lat, lon, prawdopodobieństwo)]."""

    def __init__(self, plik):
        with np.load(plik) as d:
            self.cechy = d["cechy"].astype(np.float32)
            self.gps = d["gps"].astype(np.float32)
            self.skala = float(d["skala"])

    def najlepsze(self, cecha: np.ndarray, k: int = 5) -> list[tuple[float, float, float]]:
        logity = self.skala * (self.cechy @ np.asarray(cecha, dtype=np.float32))
        logity -= logity.max()
        p = np.exp(logity)
        p /= p.sum()
        idx = np.argpartition(-p, k)[:k]
        idx = idx[np.argsort(-p[idx])]
        return [(round(float(self.gps[i][0]), 5), round(float(self.gps[i][1]), 5), round(float(p[i]), 4)) for i in idx]


# --- pobieranie modelu -------------------------------------------------------------------------------------------------------
def folder(katalog_modeli) -> Path:
    return Path(katalog_modeli) / "geoclip"


def pobrany(katalog_modeli) -> bool:
    f = folder(katalog_modeli)
    return (f / PLIK_MODELU).is_file() and (f / PLIK_GALERII).is_file()


def stan(katalog_modeli) -> dict:
    with _blokada:
        s = dict(_stan)
    return {**s, "pobrany": pobrany(katalog_modeli)}


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for kawalek in iter(lambda: f.read(1 << 20), b""):
            h.update(kawalek)
    return h.hexdigest()


def _pobierz_plik(url: str, cel: Path, postep) -> None:
    tmp = cel.with_name(cel.name + ".pobieranie")
    zad = urllib.request.Request(url, headers={"User-Agent": "Katalogator"})
    with urllib.request.urlopen(zad, timeout=60) as r, open(tmp, "wb") as f:  # noqa: S310 — stały adres wydania na GitHubie
        razem = int(r.headers.get("Content-Length") or 0)
        mam = 0
        for kawalek in iter(lambda: r.read(1 << 20), b""):
            f.write(kawalek)
            mam += len(kawalek)
            postep(mam, razem)
    os.replace(tmp, cel)


def pobierz(katalog_modeli) -> dict:
    with _blokada:
        if _stan["trwa"]:
            return {"blad": "Pobieranie modelu już trwa."}
        _stan.update(trwa=True, zrobione=0, wszystkie=0, komunikat="Pobieram model rozpoznawania miejsca…", blad="")
    threading.Thread(target=_pobierz, args=(Path(katalog_modeli),), daemon=True, name="geoclip-pobieranie").start()
    return {"ok": True}


def _pobierz(katalog_modeli: Path) -> None:
    f = folder(katalog_modeli)
    f.mkdir(parents=True, exist_ok=True)
    try:
        sumy = dict(SUMY)
        if not all(sumy.values()):
            with urllib.request.urlopen(urllib.request.Request(WYDANIE + "geoclip-sumy.json", headers={"User-Agent": "Katalogator"}),
                                        timeout=30) as r:  # noqa: S310
                sumy.update({k: v for k, v in json.loads(r.read().decode()).items() if k in SUMY and not sumy.get(k)})
        for n in (PLIK_MODELU, PLIK_GALERII):
            cel = f / n
            if cel.is_file() and _sha(cel) == sumy[n]:
                continue

            def postep(mam, razem, n=n):
                with _blokada:
                    _stan.update(zrobione=mam // 1048576, wszystkie=razem // 1048576, komunikat=f"Pobieram {n}…")
            _pobierz_plik(WYDANIE + n, cel, postep)
            if _sha(cel) != sumy[n]:
                cel.unlink(missing_ok=True)
                raise ValueError(f"{n}: suma kontrolna się nie zgadza — plik usunięty.")
        with _blokada:
            _stan.update(trwa=False, komunikat="Model gotowy.")
    except Exception as e:  # noqa: BLE001 — błąd ma trafić do panelu
        LOG.exception("GeoCLIP: pobieranie")
        with _blokada:
            _stan.update(trwa=False, blad=f"Nie udało się pobrać modelu: {e}", komunikat="")


# --- przewidywanie -----------------------------------------------------------------------------------------------------------
def _zaladuj(katalog_modeli):
    global _model
    if _model is None:
        import onnxruntime as ort
        f = folder(katalog_modeli)
        opcje = ort.SessionOptions()
        opcje.intra_op_num_threads = max(1, (os.cpu_count() or 2) - 1)
        _model = (ort.InferenceSession(str(f / PLIK_MODELU), opcje, providers=["CPUExecutionProvider"]), Galeria(f / PLIK_GALERII))
    return _model


def przewiduj(katalog_modeli, sciezka, k: int = 3) -> list[tuple[float, float, float]]:
    """Najbardziej prawdopodobne miejsca zdjęcia: [(lat, lon, p)]; pusta lista, gdy obrazu nie da się odczytać."""
    sesja, galeria = _zaladuj(katalog_modeli)
    try:
        x = przygotuj(sciezka)[None]
    except (OSError, ValueError):
        return []
    cecha = sesja.run(None, {"pixel_values": x})[0][0]
    return galeria.najlepsze(cecha, k)
