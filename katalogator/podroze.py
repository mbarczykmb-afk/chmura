"""✈ Podróże: dziennik wypraw (oś czasu Google, trasy GPS, szczyty, rezerwacje, zdjęcia) jako część Katalogatora.

Aplikacja (HTML + JS w `ui/podroze/`) jest serwowana przez serwer Katalogatora pod `/podroze/` — bez Node.js, bez
osobnego portu. Dane podróży (historia lokalizacji, trasy, rezerwacje) leżą w folderze danych programu
(`%LOCALAPPDATA%\\Katalogator\\podroze\\dane`) i nigdy nie trafiają do repozytorium ani na zewnątrz; do pliku danych
trafiają przez „Importuj” z dotychczasowego folderu projektu. Zdjęcia są odczytywane tylko z folderów, które Katalogator
zna jako bibliotekę (miejsce docelowe projektów, foldery Przeglądarki, dodatkowe foldery z ustawień).
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
import shutil
import threading
import time
from pathlib import Path

LOG = logging.getLogger("katalogator.podroze")

UI_PODROZE = Path(__file__).parent / "ui" / "podroze"

# Pliki danych aplikacji (serwowane z folderu danych); sample-trips.json to jedyny obowiązkowy
DANE_PLIKI = ("sample-trips.json", "sample-data.js", "user-photos-index.js", "matched_user_photos.json",
              "user_photos_dec2025.json", "user_photos_zakopane.json", "places_cache.json", "sample-madera.json")
ZDJECIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
           ".gif": "image/gif", ".bmp": "image/bmp"}   # bez SVG: otwarty wprost mógłby uruchomić skrypt
_TYPY_STATYCZNE = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                   ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
                   ".woff2": "font/woff2", ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon"}


def folder_danych(katalog) -> Path:
    return Path(katalog) / "podroze" / "dane"


def domyslny_folder() -> str:
    """Typowe miejsce dotychczasowego projektu (Antigravity) — podpowiedź przy imporcie."""
    p = Path.home() / ".gemini" / "antigravity" / "scratch" / "google-timeline-travels"
    return str(p) if (p / "sample-trips.json").is_file() else ""


# --- dane ------------------------------------------------------------------------------------------------------------
_licznik: dict[str, tuple[float, int]] = {}


def liczba_wypraw(plik: Path) -> int:
    """Liczba wypraw w pliku — parsujemy raz na zmianę pliku (aplikacja pyta o wersję co kilka sekund)."""
    try:
        mt = plik.stat().st_mtime
    except OSError:
        return 0
    k = str(plik)
    if k in _licznik and _licznik[k][0] == mt:
        return _licznik[k][1]
    try:
        d = json.loads(plik.read_text(encoding="utf-8"))
        n = len(d["trips"]) if isinstance(d, dict) and isinstance(d.get("trips"), list) else (len(d) if isinstance(d, list) else 0)
    except (OSError, ValueError):
        n = 0
    _licznik[k] = (mt, n)
    return n


def wersja(katalog) -> dict:
    plik = folder_danych(katalog) / "sample-trips.json"
    try:
        mt = int(plik.stat().st_mtime * 1000)
    except OSError:
        mt = 0
    return {"version": mt, "totalTrips": liczba_wypraw(plik) if mt else 0, "serverTime": int(time.time() * 1000)}


_import = {"trwa": False, "zrobione": 0, "wszystkie": 0, "komunikat": "", "blad": "", "koniec": 0.0}
_blokada = threading.Lock()


def stan(katalog, ust: dict, korzenie: list[str]) -> dict:
    d = folder_danych(katalog)
    plik = d / "sample-trips.json"
    ma = plik.is_file()
    mb = sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1048576 if d.is_dir() else 0
    with _blokada:
        imp = dict(_import)
    return {"ma_dane": ma, "wyprawy": liczba_wypraw(plik) if ma else 0, "rozmiar_mb": round(mb, 1),
            "zaimportowano": plik.stat().st_mtime if ma else None, "import": imp,
            "podpowiedz": domyslny_folder(), "folder_importu": ust.get("folder_importu") or "",
            "korzenie": korzenie, "dodatkowe": list(ust.get("korzenie") or [])}


def importuj(katalog, folder: str) -> dict:
    """Kopiuje dane z dotychczasowego folderu projektu do folderu danych programu (w tle)."""
    kat = Path(folder or "")
    if not folder or not kat.is_dir():
        return {"blad": "Nie ma takiego folderu."}
    if not (kat / "sample-trips.json").is_file():
        return {"blad": "W tym folderze nie ma pliku sample-trips.json — wskaż główny folder projektu Timeline Travels, "
                        "w którym są wygenerowane dane wypraw."}
    pliki = [kat / n for n in DANE_PLIKI if (kat / n).is_file()]
    mini = [p for p in sorted((kat / "thumbnails").glob("*")) if p.suffix.lower() in ZDJECIA] if (kat / "thumbnails").is_dir() else []
    with _blokada:
        if _import["trwa"]:
            return {"blad": "Import już trwa."}
        _import.update(trwa=True, zrobione=0, wszystkie=len(pliki) + len(mini), komunikat="Kopiuję dane podróży…", blad="")
    threading.Thread(target=_kopiuj, args=(Path(katalog), pliki, mini), daemon=True, name="podroze-import").start()
    return {"ok": True}


def _kopiuj(katalog: Path, pliki: list[Path], mini: list[Path]) -> None:
    cel = folder_danych(katalog)
    try:
        (cel / "thumbnails").mkdir(parents=True, exist_ok=True)
        # sample-trips.json na końcu: dopiero on „odblokowuje” widok wypraw, a reszta jest już na miejscu
        kolejka = [(p, cel / p.name) for p in pliki if p.name != "sample-trips.json"] + \
                  [(p, cel / "thumbnails" / p.name) for p in mini] + \
                  [(p, cel / p.name) for p in pliki if p.name == "sample-trips.json"]
        for i, (z, do) in enumerate(kolejka, 1):
            tmp = do.with_name(do.name + ".nowy")
            shutil.copyfile(z, tmp)
            os.replace(tmp, do)
            with _blokada:
                _import.update(zrobione=i, komunikat=f"Kopiuję: {z.name}")
        _licznik.clear()
        try:   # świeżo zaimportowane wyprawy dostają zapamiętane ślady GPS (bez sieci)
            from . import slady
            slady.zloz(katalog)
        except Exception:  # noqa: BLE001 — brak śladów nie może psuć importu
            LOG.exception("Podróże: składanie śladów po imporcie")
        with _blokada:
            _import.update(trwa=False, koniec=time.time(), komunikat=f"Gotowe — skopiowano {len(kolejka)} plików.")
    except OSError as e:
        LOG.exception("Podróże: błąd importu")
        with _blokada:
            _import.update(trwa=False, blad=f"Import nie powiódł się: {e}", komunikat="")


def usun_dane(katalog) -> dict:
    with _blokada:
        if _import["trwa"]:
            return {"blad": "Poczekaj, aż skończy się import."}
    shutil.rmtree(folder_danych(katalog), ignore_errors=True)
    _licznik.clear()
    with _blokada:
        _import.update(zrobione=0, wszystkie=0, komunikat="", blad="")
    return {"ok": True}


def plik_danych(katalog, nazwa: str) -> Path | None:
    """Plik danych aplikacji z listy dozwolonych albo miniatura z thumbnails/ — nigdy nic spoza folderu danych."""
    d = folder_danych(katalog)
    if nazwa in DANE_PLIKI:
        p = d / nazwa
    elif nazwa.startswith("slady/") and nazwa.count("/") == 1:   # ślady GPS wyprawy (Strava / Intervals.icu)
        from . import slady
        return slady.plik_wyprawy(katalog, nazwa[6:])
    elif nazwa.startswith("thumbnails/") and nazwa.count("/") == 1 and Path(nazwa).suffix.lower() in ZDJECIA \
            and ".." not in nazwa and "\\" not in nazwa:
        p = d / nazwa
    else:
        return None
    return p if p.is_file() else None


def zdjecia_json(katalog) -> Path | None:
    """Lista dopasowanych zdjęć dla /api/user-photos — jak w oryginale: najpierw grudzień 2025, potem pełna."""
    for n in ("user_photos_dec2025.json", "matched_user_photos.json"):
        p = folder_danych(katalog) / n
        if p.is_file():
            return p
    return None


# --- zdjęcia z biblioteki ------------------------------------------------------------------------------------------------
def _pod(sciezka: str, korzenie: list[str]) -> bool:
    a = os.path.normcase(sciezka)
    for k in korzenie:
        try:
            b = os.path.normcase(os.path.realpath(k)).rstrip("\\/")
        except (OSError, ValueError):
            continue
        if b and (a == b or a.startswith(b + os.sep)):
            return True
    return False


def rozwiaz_zdjecie(zadanie: str, korzenie: list[str], katalog, szukaj=None) -> tuple[Path | None, str]:
    """(plik, kod): kod = ok | brak | zabronione. Ścieżka bezwzględna musi leżeć w folderze biblioteki;
    sama nazwa pliku jest szukana w miniaturach podróży, a potem w bazie Przeglądarki (szukaj(nazwa) → ścieżka)."""
    zadanie = (zadanie or "").strip()
    if not zadanie or "\x00" in zadanie or Path(zadanie).suffix.lower() not in ZDJECIA:
        return None, "zabronione" if zadanie else "brak"
    if re.match(r"^[a-zA-Z]:[\\/]", zadanie) or zadanie.startswith(("\\\\", "/")):
        try:
            p = os.path.realpath(zadanie)
        except (OSError, ValueError):
            return None, "brak"
        if not _pod(p, korzenie):
            return None, "zabronione"
        return (Path(p), "ok") if os.path.isfile(p) else (None, "brak")
    nazwa = re.split(r"[\\/]", zadanie)[-1]
    mini = folder_danych(katalog) / "thumbnails" / nazwa
    if mini.is_file():
        return mini, "ok"
    if szukaj:
        try:
            znaleziony = szukaj(nazwa)
        except Exception:  # noqa: BLE001 — baza Przeglądarki zajęta / brak: po prostu nie ma
            znaleziony = None
        if znaleziony and os.path.isfile(znaleziony) and _pod(os.path.realpath(znaleziony), korzenie):
            return Path(znaleziony), "ok"
    return None, "brak"


def zastepcze_svg(nazwa: str) -> bytes:
    n = html.escape(nazwa or "")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300"><rect width="100%" height="100%" fill="#0f172a" rx="12"/>'
            f'<text x="200" y="130" font-size="36" text-anchor="middle" fill="#64748b">📷</text>'
            f'<text x="200" y="175" font-family="system-ui,sans-serif" font-weight="bold" font-size="14" text-anchor="middle" fill="#f8fafc">{n}</text>'
            f'<text x="200" y="200" font-family="system-ui,sans-serif" font-size="11" text-anchor="middle" fill="#94a3b8">'
            f'Brak pliku — podłącz dysk ze zdjęciami</text></svg>').encode("utf-8")


# --- odpowiedzi serwera --------------------------------------------------------------------------------------------------
def odpowiedz_get(katalog, rel: str, q: dict, korzenie: list[str], szukaj=None) -> tuple:
    """Co odpowiedzieć na GET /podroze/<rel>. Zwraca:
    ("plik", Path, typ, cache) | ("bajty", dane, typ) | ("json", obiekt) | ("brak",) | ("zabronione",)."""
    if rel == "api/version":
        return ("json", wersja(katalog))
    if rel == "api/user-photos":
        p = zdjecia_json(katalog)
        return ("plik", p, "application/json; charset=utf-8", "no-cache") if p else ("json", {"error": "No indexed photos found"}, 404)
    if rel == "api/photo":
        zadanie = (q.get("path") or q.get("file") or [""])[0]
        p, kod = rozwiaz_zdjecie(zadanie, korzenie, katalog, szukaj)
        if kod == "zabronione":
            return ("zabronione",)
        if p is None:
            return ("bajty", zastepcze_svg(re.split(r"[\\/]", zadanie)[-1]), "image/svg+xml; charset=utf-8")
        return ("plik", p, ZDJECIA[p.suffix.lower()], "private, max-age=86400")
    if rel.startswith("api/"):
        return ("brak",)
    d = plik_danych(katalog, rel)
    if d:
        typ = ZDJECIA.get(d.suffix.lower()) or _TYPY_STATYCZNE.get(d.suffix.lower(), "application/octet-stream")
        return ("plik", d, typ, "private, max-age=3600" if rel.startswith("thumbnails/") else "no-cache")
    # pliki aplikacji (HTML/JS/CSS) — tylko z katalogu ui/podroze, nigdy spoza niego
    p = (UI_PODROZE / rel).resolve()
    if rel and UI_PODROZE.resolve() in p.parents and p.suffix in _TYPY_STATYCZNE and p.is_file():
        return ("plik", p, _TYPY_STATYCZNE[p.suffix], "no-cache")
    return ("brak",)


def wyslij_plik(h, sciezka: Path, typ: str, cache: str = "no-cache") -> None:
    """Plik z obsługą zakresów (Range) i bez wczytywania całości do pamięci (dane podróży mają dziesiątki MB)."""
    try:
        rozm = os.path.getsize(sciezka)
    except OSError:
        h.send_response(404)
        h.send_header("Content-Length", "0")
        h.end_headers()
        return
    start, koniec = 0, max(0, rozm - 1)
    m = re.match(r"bytes=(\d*)-(\d*)", h.headers.get("Range", ""))
    if m and (m.group(1) or m.group(2)) and rozm:
        if m.group(1):
            start = int(m.group(1))
            koniec = min(int(m.group(2)) if m.group(2) else rozm - 1, rozm - 1)
        else:
            start = max(0, rozm - int(m.group(2)))
        if start > koniec:
            h.send_response(416)
            h.send_header("Content-Range", f"bytes */{rozm}")
            h.end_headers()
            return
        h.send_response(206)
        h.send_header("Content-Range", f"bytes {start}-{koniec}/{rozm}")
    else:
        h.send_response(200)
    dlugosc = koniec - start + 1 if rozm else 0
    h.send_header("Content-Type", typ)
    h.send_header("Accept-Ranges", "bytes")
    h.send_header("Content-Length", str(dlugosc))
    h.send_header("Cache-Control", cache)
    h.end_headers()
    if h.command == "HEAD" or not dlugosc:
        return
    with open(sciezka, "rb") as f:
        f.seek(start)
        zostalo = dlugosc
        while zostalo > 0:
            kawalek = f.read(min(1 << 16, zostalo))
            if not kawalek:
                break
            h.wfile.write(kawalek)
            zostalo -= len(kawalek)
