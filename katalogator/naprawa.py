"""🛠 Naprawa odzyskanych (albo po prostu uszkodzonych) filmów.

1. Diagnoza MP4/MOV: z jakich „pudełek” (atomów) składa się plik — `ftyp` (nagłówek), `mdat` (obraz i dźwięk),
   `moov` (indeks: gdzie zaczyna się każda klatka). Bez `moov` odtwarzacz nie wie, jak czytać `mdat`
   (Windows: „Nie można odtworzyć… 0xc00d36e5”), choć dane filmu w pliku są.
2. Naprawa ffmpeg: przepisanie pliku z pominięciem uszkodzonych fragmentów (indeks jest, ale plik ucięty, zepsute
   pakiety, AVI/MKV/MPG po odzyskaniu).
3. Brak indeksu: odbudowa programem **untrunc** (darmowy, open source) na podstawie *wzorca* — działającego filmu
   z tego samego źródła (ten sam telefon / aparat / Zoom); untrunc pobierany jest raz z GitHuba.
Wynik zawsze obok oryginału: `<nazwa>_naprawiony.<rozszerzenie>` — oryginał zostaje bez zmian.
"""

from __future__ import annotations

import io
import json
import os
import struct
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from . import filmy

MP4 = {".mp4", ".mov", ".m4v", ".3gp", ".3g2"}
ATOMY = {b"ftyp", b"moov", b"mdat", b"free", b"skip", b"wide", b"uuid", b"udta", b"meta", b"pdin", b"moof", b"mfra",
         b"sidx", b"styp", b"emsg"}
UNTRUNC_REPO = "anthwlock/untrunc"
BEZ_OKNA = 0x08000000 if sys.platform == "win32" else 0


def atomy(sciezka: str, limit: int = 200) -> tuple[list[tuple[str, int, int]], bool]:
    """Atomy najwyższego poziomu: [(typ, początek, rozmiar)], ucięty (ostatni atom wychodzi poza koniec pliku)."""
    wynik, uciety = [], False
    rozm = os.path.getsize(sciezka)
    with open(sciezka, "rb") as f:
        poz = 0
        while poz + 8 <= rozm and len(wynik) < limit:
            f.seek(poz)
            nagl = f.read(16)
            dl, typ = struct.unpack(">I4s", nagl[:8])
            if dl == 1 and len(nagl) >= 16:
                dl = struct.unpack(">Q", nagl[8:16])[0]
            elif dl == 0:
                dl = rozm - poz
            if typ not in ATOMY or dl < 8:
                break
            if poz + dl > rozm:
                uciety = True
            wynik.append((typ.decode("latin-1"), poz, dl))
            poz += dl
    return wynik, uciety


def to_tekst(sciezka: str) -> bool:
    """Plik tekstowy z rozszerzeniem filmu (np. „.d.mts” — kod TypeScript), a nie film."""
    try:
        with open(sciezka, "rb") as f:
            d = f.read(512)
    except OSError:
        return False
    if not d:
        return False
    drukowalne = sum(1 for b in d if 32 <= b < 127 or b in (9, 10, 13))
    return drukowalne / len(d) > 0.95


def ftyp(sciezka: str) -> tuple[str, list[str]] | None:
    """„Podpis” programu, który nagrał film: główna marka i zgodne marki z atomu ftyp (np. isom / mp42 / qt)."""
    try:
        with open(sciezka, "rb") as f:
            d = f.read(64)
    except OSError:
        return None
    if len(d) < 16 or d[4:8] != b"ftyp":
        return None
    n = min(int.from_bytes(d[:4], "big"), len(d))
    marki = [d[i:i + 4].decode("latin-1") for i in range(16, n - 3, 4)]
    return d[8:12].decode("latin-1"), [m for m in marki if m.strip("\0")]


def kandydaci(uszkodzony: str, filmy: list[str], limit: int = 5, pomin: str = "") -> list[str]:
    """Działające filmy najbardziej podobne do uszkodzonego (ta sama marka ftyp, podobny rozmiar) — wzorce dla
    untrunc. `filmy` — ścieżki filmów znanych programowi (biblioteka, Przeglądarka, foldery użytkownika)."""
    cel = ftyp(uszkodzony)
    rozm = os.path.getsize(uszkodzony) or 1
    oceny = []
    for p in filmy[:4000]:
        if pomin and os.path.normcase(p).startswith(os.path.normcase(pomin)):
            continue
        if os.path.splitext(p)[1].lower() not in MP4:
            continue
        f = ftyp(p)
        if not f:
            continue
        try:
            a, uciety = atomy(p, 20)
            r = os.path.getsize(p)
        except OSError:
            continue
        if uciety or "moov" not in [t for t, _, _ in a]:
            continue  # wzorzec musi sam działać
        ocena = 0
        if cel:
            ocena += 4 * (f[0] == cel[0]) + len(set(f[1]) & set(cel[1]))
        ocena += 1 if rozm / 5 <= r <= rozm * 50 else 0
        oceny.append((ocena, -abs(r - rozm), p))
    oceny.sort(reverse=True)
    return [p for _, _, p in oceny[:limit]]


def diagnoza(sciezka: str) -> dict:
    e = os.path.splitext(sciezka)[1].lower()
    d = {"sciezka": sciezka, "nazwa": os.path.basename(sciezka), "rozmiar": os.path.getsize(sciezka), "mp4": e in MP4}
    if to_tekst(sciezka):
        return {**d, "sposob": None, "tekst": True,
                "opis": "To plik tekstowy z rozszerzeniem filmu (np. kod programu „.d.mts”), a nie film — pomijam."}
    if not d["mp4"]:
        d["opis"] = "Spróbuję przepisać plik programem ffmpeg z pominięciem uszkodzonych fragmentów."
        d["sposob"] = "ffmpeg"
        return d
    try:
        a, uciety = atomy(sciezka)
    except OSError as er:
        return {**d, "opis": f"Nie da się odczytać: {er.strerror or er}", "sposob": None}
    typy = [t for t, _, _ in a]
    d.update(atomy=typy, moov="moov" in typy, mdat="mdat" in typy, ftyp="ftyp" in typy, uciety=uciety)
    if d["moov"]:
        d["sposob"] = "ffmpeg"
        d["opis"] = ("Indeks jest" + (", ale plik jest ucięty" if uciety else "") +
                     " — przepiszę go programem ffmpeg (zwykle wystarcza).")
    elif d["mdat"] or d["ftyp"]:
        d["sposob"] = "wzorzec"
        d["opis"] = ("Brak indeksu (moov) — dane filmu są, ale odtwarzacz nie wie, jak je czytać. Odbuduję indeks "
                     "na podstawie wzorca: działającego filmu z tego samego źródła (np. inne nagranie Zoom albo film "
                     "z tego samego telefonu).")
    else:
        d["sposob"] = None
        d["opis"] = "To nie wygląda na film MP4 (nieznany początek pliku) — tego nie naprawię."
    return d


def _wynik(sciezka: str) -> str:
    rdzen, e = os.path.splitext(sciezka)
    p = f"{rdzen}_naprawiony{e or '.mp4'}"
    i = 2
    while os.path.exists(p):
        p = f"{rdzen}_naprawiony{i}{e or '.mp4'}"
        i += 1
    return p


def _dziala(sciezka: str) -> bool:
    """Naprawiony film: ffmpeg czyta z niego klatkę."""
    try:
        return os.path.getsize(sciezka) > 1024 and bool(filmy.klatka(sciezka, 160, 0.5))
    except OSError:
        return False


def napraw_ffmpeg(sciezka: str) -> dict:
    f = filmy.ffmpeg()
    if not f:
        return {"blad": "Brak ffmpeg — zainstaluj Katalogator z instalatora (ffmpeg jest w zestawie)."}
    cel = _wynik(sciezka)
    e = os.path.splitext(sciezka)[1].lower()
    cmd = [f, "-hide_banner", "-v", "error", "-err_detect", "ignore_err", "-fflags", "+genpts+discardcorrupt",
           "-i", sciezka, "-map", "0:v?", "-map", "0:a?", "-c", "copy"]
    if e in MP4:
        cmd += ["-movflags", "+faststart"]
    cmd += ["-y", cel]
    try:
        w = subprocess.run(cmd, capture_output=True, text=True, timeout=600, creationflags=BEZ_OKNA)
    except (OSError, subprocess.SubprocessError) as er:
        return {"blad": f"ffmpeg: {er}"}
    if os.path.exists(cel) and _dziala(cel):
        return {"ok": True, "sciezka": cel, "sposob": "ffmpeg"}
    try:
        os.remove(cel)
    except OSError:
        pass
    return {"blad": "ffmpeg nie odczytał tego filmu" + (f": {w.stderr.strip().splitlines()[-1][:200]}"
                                                         if w.stderr.strip() else "") + "."}


# --- untrunc: odbudowa indeksu MP4 z wzorca ---------------------------------------------------------------
def untrunc(katalog: Path) -> str | None:
    pliki = [p for p in Path(katalog, "untrunc").rglob("untrunc*.exe" if sys.platform == "win32" else "untrunc*")
             if p.is_file() and "gui" not in p.name.lower()]  # wersja z oknem nie przyjmuje poleceń
    if pliki:
        return str(pliki[0])
    from shutil import which
    return which("untrunc")


def pobierz_untrunc(katalog: Path) -> dict:
    """Najnowsze wydanie untrunc dla Windows z GitHuba (archiwum .zip) → <dane programu>/untrunc."""
    if sys.platform != "win32":
        return {"blad": "Automatyczne pobieranie untrunc działa w Windows; w innych systemach zainstaluj untrunc sam."}
    try:
        with urllib.request.urlopen(f"https://api.github.com/repos/{UNTRUNC_REPO}/releases/latest", timeout=20) as r:
            info = json.load(r)
        zipy = [a for a in info.get("assets", []) if a["name"].lower().endswith(".zip")
                and ("win" in a["name"].lower() or "x64" in a["name"].lower() or "64" in a["name"])]
        zasob = next((a for a in zipy if "gui" not in a["name"].lower()), zipy[0] if zipy else None)
        if not zasob:
            return {"blad": "Nie znalazłem wersji untrunc dla Windows — pobierz ręcznie: "
                            f"https://github.com/{UNTRUNC_REPO}/releases"}
        with urllib.request.urlopen(zasob["browser_download_url"], timeout=120) as r:
            dane = r.read()
        cel = Path(katalog, "untrunc")
        cel.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(dane)) as z:
            for n in z.namelist():  # bez ścieżek wychodzących poza folder
                if ".." in Path(n).parts or Path(n).is_absolute():
                    continue
                z.extract(n, cel)
    except (OSError, ValueError, zipfile.BadZipFile) as er:
        return {"blad": f"Nie udało się pobrać untrunc: {er}"}
    exe = untrunc(katalog)
    return {"ok": True, "untrunc": exe} if exe else {"blad": "W pobranym archiwum nie ma untrunc.exe."}


def napraw_wzorcem(sciezka: str, wzorzec: str, katalog: Path) -> dict:
    if not wzorzec or not os.path.isfile(wzorzec):
        return {"blad": "Wskaż wzorzec — działający film z tego samego źródła."}
    exe = untrunc(katalog)
    if not exe:
        w = pobierz_untrunc(katalog)
        if "blad" in w:
            return w
        exe = w["untrunc"]
    try:
        w = subprocess.run([exe, "-s", wzorzec, sciezka], capture_output=True, text=True, timeout=1800,
                           cwd=os.path.dirname(sciezka), creationflags=BEZ_OKNA)
    except (OSError, subprocess.SubprocessError) as er:
        return {"blad": f"untrunc: {er}"}
    # untrunc zapisuje obok: „<plik>_fixed.mp4”, „<plik>_fixed-s.mp4”, „<rdzeń>_fixed.mp4” — zależnie od wersji
    folder, nazwa = os.path.split(sciezka)
    rdzen = os.path.splitext(nazwa)[0]
    gotowe = sorted((os.path.join(folder, n) for n in os.listdir(folder)
                     if (n.startswith(nazwa + "_fixed") or n.startswith(rdzen + "_fixed")) and n != nazwa),
                    key=os.path.getmtime, reverse=True)
    gotowy = gotowe[0] if gotowe else None
    if gotowy and _dziala(gotowy):
        cel = _wynik(sciezka)
        os.replace(gotowy, cel)
        return {"ok": True, "sciezka": cel, "sposob": "wzorzec"}
    for p in gotowe:  # nieudana próba z tym wzorcem — bez śmieci obok odzyskanych plików
        try:
            os.remove(p)
        except OSError:
            pass
    tekst = (w.stdout + w.stderr).strip().splitlines()
    return {"blad": "Nie udało się odbudować indeksu" + (f": {tekst[-1][:200]}" if tekst else "") +
                    " — spróbuj innego wzorca (to samo urządzenie / program, podobne ustawienia nagrywania)."}


def napraw(sciezka: str, katalog: Path, wzorzec: str | None = None) -> dict:
    d = diagnoza(sciezka)
    if d.get("sposob") == "ffmpeg":
        return {**napraw_ffmpeg(sciezka), "diagnoza": d}
    if d.get("sposob") == "wzorzec":
        if not wzorzec:
            w = napraw_ffmpeg(sciezka)  # czasem ffmpeg i tak coś odczyta
            if w.get("ok"):
                return {**w, "diagnoza": d}
            return {"potrzebny_wzorzec": True, "diagnoza": d, "blad": d["opis"]}
        return {**napraw_wzorcem(sciezka, wzorzec, katalog), "diagnoza": d}
    return {"blad": d.get("opis") or "Nie da się naprawić.", "diagnoza": d}


def napraw_auto(sciezka: str, katalog: Path, filmy: list[str], pamiec: dict, pomin: str = "") -> dict:
    """Bez pytania o wzorzec: ffmpeg, a gdy brak indeksu — po kolei najbardziej podobne działające filmy z dysków
    jako wzorce (ten, który zadziałał, jest próbowany najpierw przy kolejnych plikach)."""
    d = diagnoza(sciezka)
    if d.get("sposob") != "wzorzec":
        return napraw(sciezka, katalog)
    w = napraw_ffmpeg(sciezka)
    if w.get("ok"):
        return {**w, "diagnoza": d}
    marka = (ftyp(sciezka) or ("?",))[0]
    proby = list(dict.fromkeys([*pamiec.get(marka, []), *kandydaci(sciezka, filmy, 4, pomin)]))[:5]
    if not proby:
        return {"blad": "Nie znalazłem na dyskach działającego filmu podobnego do tego (wzorca) — wskaż go ręcznie.",
                "potrzebny_wzorzec": True, "diagnoza": d}
    ostatni = None
    for wz in proby:
        r = napraw_wzorcem(sciezka, wz, katalog)
        if r.get("ok"):
            pamiec.setdefault(marka, [])
            if wz not in pamiec[marka]:
                pamiec[marka].insert(0, wz)
            return {**r, "wzorzec": wz, "diagnoza": d}
        ostatni = r
        if "untrunc" in (r.get("blad") or "") and "pobrać" in (r.get("blad") or ""):
            return {**r, "diagnoza": d}  # bez untrunc dalsze próby nic nie dadzą
    return {"blad": f"Nie udało się odbudować indeksu (sprawdzone wzorce: {len(proby)}) — "
                    + ((ostatni or {}).get("blad") or "")[:200], "diagnoza": d}


def filmy_w(folder: str, limit: int = 300) -> list[dict]:
    """Filmy w folderze (do wyboru wzorca) — najpierw te z tym samym rozszerzeniem co naprawiane."""
    try:
        return sorted(({"sciezka": w.path, "nazwa": w.name, "rozmiar": w.stat().st_size} for w in os.scandir(folder)
                       if w.is_file() and os.path.splitext(w.name)[1].lower() in MP4 | {".avi", ".mkv", ".mts"}),
                      key=lambda x: x["nazwa"].lower())[:limit]
    except OSError:
        return []
