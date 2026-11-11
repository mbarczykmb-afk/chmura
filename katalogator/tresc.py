"""🧠 Wyszukiwanie zdjęć po treści („plaża”, „pies na śniegu”, „tort urodzinowy”) — CLIP, w całości lokalnie.

Model (budowany w CI: narzedzia/clip/zbuduj.py, wydanie clip-model-1, pobierany przy pierwszym użyciu, ok. 230 MB):
  clip-obraz-int8.onnx  — koder obrazu CLIP ViT-B/32 (obraz 224×224 → znormalizowany wektor 512)
  clip-tekst-int8.onnx  — wielojęzyczny koder tekstu (DistilBERT, także po polsku) w tej samej przestrzeni 512
  clip-slownik.txt      — słownik WordPiece kodera tekstu (tokenizacja niżej, bez dodatkowych bibliotek)
Wektory zdjęć (float16) leżą we własnej bazie modelu (<dane>/modele/clip/wektory.db, klucz: ścieżka + data pliku)
— liczone raz, w tle, tylko dla nowych zdjęć; korzystają z nich wszystkie widoki (Przeglądarka, biblioteka projektu).
Zdjęcia nigdzie nie są wysyłane.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import unicodedata
import urllib.request
from pathlib import Path

import numpy as np

LOG = logging.getLogger("katalogator.tresc")

WYDANIE = "https://github.com/mbarczykmb-afk/chmura/releases/download/clip-model-1/"
PLIKI = ("clip-obraz-int8.onnx", "clip-tekst-int8.onnx", "clip-slownik.txt")
# SHA-256 z wydania clip-model-1 (None → z pliku clip-sumy.json z tego samego wydania)
SUMY: dict[str, str | None] = {
    "clip-obraz-int8.onnx": "24e42d2379f42310c43b35b406ff255f025913894ce022573c60776deaebe1df",
    "clip-tekst-int8.onnx": "123736dfc70590dc9f67b92aa8ba9e72ba3dcf9e94bb3a99063ed6d3699c111c",
    "clip-slownik.txt": "fe0fda7c425b48c516fc8f160d594c8022a0808447475c1a7c6d6479763f310c"}
MAKS_TOKENOW = 64
PROG = 0.23          # podobieństwo (cosinus) poniżej tego — to już nie „to samo” (tło: ok. 0,18–0,24)
ODSTEP = 0.06        # … i nie dalej niż tyle od najlepszego trafienia (próg względny)
WYNIKOW = 400        # najwyżej tyle zdjęć „podobnych treścią” w jednym wyszukiwaniu

SCHEMAT = "CREATE TABLE IF NOT EXISTS g_clip (sciezka TEXT PRIMARY KEY, mtime REAL, wektor BLOB NOT NULL);"

KATALOG_MODELI: Path | None = None   # <dane>/modele — ustawia aplikacja
_stan = {"trwa": False, "zrobione": 0, "wszystkie": 0, "komunikat": "", "blad": "", "etap": ""}
_blokada = threading.Lock()
_przerwij = threading.Event()
_model: dict = {}
_pamiec: dict = {}   # baza → (liczba wektorów, max rowid, ścieżki, macierz)


def folder() -> Path:
    return Path(KATALOG_MODELI or ".") / "clip"


def _baza():
    import sqlite3
    folder().mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(folder() / "wektory.db"), timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(SCHEMAT)
    return db


def pobrany() -> bool:
    return all((folder() / n).is_file() for n in PLIKI)


# --- tokenizacja WordPiece (jak BertTokenizer „cased”: bez zmiany wielkości liter i akcentów) -----------------------
def _interp(c: str) -> bool:
    o = ord(c)
    if 33 <= o <= 47 or 58 <= o <= 64 or 91 <= o <= 96 or 123 <= o <= 126:
        return True
    return unicodedata.category(c).startswith("P")


def _chinski(o: int) -> bool:
    return (0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0x20000 <= o <= 0x2A6DF or 0x2A700 <= o <= 0x2B73F
            or 0x2B740 <= o <= 0x2B81F or 0x2B820 <= o <= 0x2CEAF or 0xF900 <= o <= 0xFAFF or 0x2F800 <= o <= 0x2FA1F)


def podziel(tekst: str) -> list[str]:
    """BasicTokenizer: czyszczenie, odstępy wokół znaków CJK i interpunkcji, podział na słowa."""
    czyste = []
    for c in tekst:
        o = ord(c)
        if o == 0 or o == 0xFFFD or (unicodedata.category(c).startswith("C") and c not in "\t\n\r"):
            continue
        if c in " \t\n\r" or unicodedata.category(c) == "Zs":
            czyste.append(" ")
        elif _chinski(o):
            czyste.append(f" {c} ")
        else:
            czyste.append(c)
    wynik = []
    for slowo in "".join(czyste).split():
        biezace = ""
        for c in slowo:
            if _interp(c):
                if biezace:
                    wynik.append(biezace)
                    biezace = ""
                wynik.append(c)
            else:
                biezace += c
        if biezace:
            wynik.append(biezace)
    return wynik


class Tokenizer:
    def __init__(self, slownik: Path):
        self.slownik = {t.rstrip("\n"): i for i, t in enumerate(slownik.read_text(encoding="utf-8").split("\n")) if t}
        self.unk, self.cls, self.sep, self.pad = (self.slownik[t] for t in ("[UNK]", "[CLS]", "[SEP]", "[PAD]"))

    def kawalki(self, slowo: str) -> list[int]:
        if len(slowo) > 100:
            return [self.unk]
        wynik, start = [], 0
        while start < len(slowo):
            koniec, znaleziony = len(slowo), None
            while start < koniec:
                kaw = ("##" if start else "") + slowo[start:koniec]
                if kaw in self.slownik:
                    znaleziony = self.slownik[kaw]
                    break
                koniec -= 1
            if znaleziony is None:
                return [self.unk]
            wynik.append(znaleziony)
            start = koniec
        return wynik

    def koduj(self, tekst: str, maks: int = MAKS_TOKENOW) -> tuple[list[int], list[int]]:
        ids = [self.cls]
        for s in podziel(tekst):
            ids += self.kawalki(s)
        ids = ids[:maks - 1] + [self.sep]
        return ids, [1] * len(ids)


# --- model -------------------------------------------------------------------------------------------------------------
def _sesje():
    if not _model:
        import onnxruntime as ort
        opcje = ort.SessionOptions()
        opcje.intra_op_num_threads = max(1, (os.cpu_count() or 2) - 1)
        f = folder()
        _model["obraz"] = ort.InferenceSession(str(f / PLIKI[0]), opcje, providers=["CPUExecutionProvider"])
        _model["tekst"] = ort.InferenceSession(str(f / PLIKI[1]), opcje, providers=["CPUExecutionProvider"])
        _model["tok"] = Tokenizer(f / PLIKI[2])
    return _model


def wektor_tekstu(tekst: str) -> np.ndarray:
    m = _sesje()
    ids, maska = m["tok"].koduj(tekst)
    w = m["tekst"].run(None, {"input_ids": np.array([ids], np.int64), "attention_mask": np.array([maska], np.int64)})[0][0]
    return (w / (np.linalg.norm(w) or 1)).astype(np.float32)


def wektory_obrazow(sciezki: list[str]) -> list[np.ndarray | None]:
    from . import geoclip   # to samo przygotowanie obrazu co w CLIP (224, wycięcie środka, normalizacja CLIP)
    m = _sesje()
    gotowe, idx = [], []
    for i, s in enumerate(sciezki):
        try:
            gotowe.append(geoclip.przygotuj(s))
            idx.append(i)
        except Exception:  # noqa: BLE001 — uszkodzony / nieobsługiwany plik
            pass
    wynik: list[np.ndarray | None] = [None] * len(sciezki)
    if gotowe:
        w = m["obraz"].run(None, {"pixel_values": np.stack(gotowe)})[0]
        w = w / np.maximum(np.linalg.norm(w, axis=1, keepdims=True), 1e-6)
        for j, i in enumerate(idx):
            wynik[i] = w[j].astype(np.float16)
    return wynik


# --- pobieranie modelu -----------------------------------------------------------------------------------------------
def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for k in iter(lambda: f.read(1 << 20), b""):
            h.update(k)
    return h.hexdigest()


def stan(galeria=None) -> dict:
    with _blokada:
        s = dict(_stan)
    s["pobrany"] = pobrany()
    try:
        if (folder() / "wektory.db").exists():
            w = _baza()
            try:
                s["zindeksowane"] = w.execute("SELECT COUNT(*) FROM g_clip").fetchone()[0]
            finally:
                w.close()
        if galeria is not None:
            db = galeria._db()
            try:
                war, arg = galeria._warunek()
                s["zdjec"] = db.execute(f"SELECT COUNT(*) FROM pliki WHERE rodzaj='zdjecie' {war}", arg).fetchone()[0]
            finally:
                db.close()
    except Exception:  # noqa: BLE001
        pass
    return s


def _ustaw(**kw) -> bool:
    with _blokada:
        _stan.update(kw)
    return not _przerwij.is_set()


def pobierz() -> dict:
    with _blokada:
        if _stan["trwa"]:
            return {"blad": "Już trwa."}
        _stan.update(trwa=True, etap="pobieranie", zrobione=0, wszystkie=0, komunikat="Pobieram model…", blad="")
    threading.Thread(target=_pobierz, daemon=True, name="clip-pobieranie").start()
    return {"ok": True}


def _pobierz() -> None:
    f = folder()
    f.mkdir(parents=True, exist_ok=True)
    try:
        sumy = dict(SUMY)
        if not all(sumy.values()):
            with urllib.request.urlopen(urllib.request.Request(WYDANIE + "clip-sumy.json", headers={"User-Agent": "Katalogator"}),
                                        timeout=30) as r:  # noqa: S310 — stały adres wydania
                sumy.update({k: v for k, v in json.loads(r.read().decode()).items() if k in SUMY and not sumy.get(k)})
        for n in PLIKI:
            cel = f / n
            if cel.is_file() and _sha(cel) == sumy[n]:
                continue
            tmp = cel.with_name(n + ".pobieranie")
            with urllib.request.urlopen(urllib.request.Request(WYDANIE + n, headers={"User-Agent": "Katalogator"}),
                                        timeout=60) as r, open(tmp, "wb") as w:  # noqa: S310
                razem, mam = int(r.headers.get("Content-Length") or 0), 0
                for k in iter(lambda: r.read(1 << 20), b""):
                    w.write(k)
                    mam += len(k)
                    _ustaw(zrobione=mam // 1048576, wszystkie=razem // 1048576, komunikat=f"Pobieram {n}…")
            if _sha(tmp) != sumy[n]:
                tmp.unlink(missing_ok=True)
                raise ValueError(f"{n}: suma kontrolna się nie zgadza — plik usunięty.")
            os.replace(tmp, cel)
        _model.clear()
        _ustaw(trwa=False, etap="", komunikat="Model gotowy — teraz „Przygotuj wyszukiwanie”.")
    except Exception as e:  # noqa: BLE001
        LOG.exception("CLIP: pobieranie")
        _ustaw(trwa=False, etap="", blad=f"Nie udało się pobrać modelu: {e}", komunikat="")


# --- indeksowanie zdjęć (w tle) -----------------------------------------------------------------------------------------
def indeksuj(galeria) -> dict:
    if not pobrany():
        return {"blad": "Najpierw pobierz model."}
    with _blokada:
        if _stan["trwa"]:
            return {"blad": "Już trwa."}
        _stan.update(trwa=True, etap="indeks", zrobione=0, wszystkie=0, komunikat="Przygotowuję wyszukiwanie po treści…",
                     blad="")
    _przerwij.clear()
    threading.Thread(target=_indeksuj, args=(galeria,), daemon=True, name="clip-indeks").start()
    return {"ok": True}


def przerwij() -> None:
    _przerwij.set()


def _indeksuj(galeria) -> None:
    try:
        db = galeria._db()
        try:
            w, arg = galeria._warunek()
            zdjecia = [(r[0], r[1]) for r in db.execute(
                f"SELECT sciezka, mtime FROM pliki WHERE rodzaj='zdjecie' {w} ORDER BY data DESC", arg)]
        finally:
            db.close()
        wb = _baza()
        try:
            znane = {r[0]: r[1] for r in wb.execute("SELECT sciezka, mtime FROM g_clip")}
            do = [(s_, mt) for s_, mt in zdjecia if znane.get(s_) is None or abs((znane[s_] or 0) - (mt or 0)) > 1]
            _ustaw(wszystkie=len(do))
            for i in range(0, len(do), 16):
                paczka = do[i:i + 16]
                wek = wektory_obrazow([s_ for s_, _ in paczka])   # odczyt z dysku POZA transakcją
                wb.executemany("INSERT OR REPLACE INTO g_clip VALUES (?,?,?)",
                               [(s_, mt or 0, v.tobytes()) for (s_, mt), v in zip(paczka, wek) if v is not None])
                wb.commit()
                if not _ustaw(zrobione=min(i + 16, len(do))):
                    _ustaw(trwa=False, etap="", komunikat="Przerwano — to, co gotowe, już działa w wyszukiwarce.")
                    return
        finally:
            wb.close()
        _pamiec.clear()
        _ustaw(trwa=False, etap="", komunikat=f"Gotowe — przejrzano {len(do)} nowych zdjęć. Szukaj np. „plaża”, „pies”, „śnieg”.")
    except Exception as e:  # noqa: BLE001
        LOG.exception("CLIP: indeks")
        _ustaw(trwa=False, etap="", blad=str(e))


# --- wyszukiwanie ---------------------------------------------------------------------------------------------------------
def gotowe() -> bool:
    """Czy wyszukiwanie po treści działa: model pobrany i są wektory choć części zdjęć."""
    if not pobrany() or not (folder() / "wektory.db").exists():
        return False
    try:
        w = _baza()
        try:
            return w.execute("SELECT 1 FROM g_clip LIMIT 1").fetchone() is not None
        finally:
            w.close()
    except Exception:  # noqa: BLE001
        return False


def _macierz():
    w = _baza()
    try:
        stan_bazy = tuple(w.execute("SELECT COUNT(*), MAX(rowid) FROM g_clip").fetchone())
        if _pamiec.get("stan") == stan_bazy:
            return _pamiec["sciezki"], _pamiec["m"]
        sciezki, wek = [], []
        for s_, v in w.execute("SELECT sciezka, wektor FROM g_clip"):
            sciezki.append(s_)
            wek.append(np.frombuffer(v, np.float16))
    finally:
        w.close()
    m = np.vstack(wek).astype(np.float32) if wek else np.zeros((0, 512), np.float32)
    _pamiec.clear()
    _pamiec.update(stan=stan_bazy, sciezki=sciezki, m=m)
    return sciezki, m


def podobne(tekst: str, dozwolone: set[str] | None = None) -> list[tuple[str, float]]:
    """[(ścieżka, podobieństwo)] od najlepszego — tylko powyżej progu i (opcjonalnie) spośród `dozwolone`."""
    sciezki, m = _macierz()
    if not sciezki:
        return []
    oceny = m @ wektor_tekstu(tekst)
    if dozwolone is not None:   # najlepsze trafienie liczone wśród dozwolonych (np. tylko zdjęcia z 2023)
        maska = np.fromiter((s_ in dozwolone for s_ in sciezki), bool, len(sciezki))
        if not maska.any():
            return []
        oceny = np.where(maska, oceny, -1.0)
    prog = max(PROG, float(oceny.max()) - ODSTEP)
    wynik = []
    for i in np.argsort(-oceny):
        if oceny[i] < prog or len(wynik) >= WYNIKOW:
            break
        if dozwolone is None or sciezki[i] in dozwolone:
            wynik.append((sciezki[i], float(oceny[i])))
    return wynik
