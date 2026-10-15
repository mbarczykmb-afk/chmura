"""🛟 Odzyskiwanie usuniętych plików.

Najpierw szybkie miejsca, gdzie usunięty plik często jeszcze jest: kosze Windows na wszystkich dyskach (także po
„Opróżnij kosz” na innym dysku), kosz programu (Odłożone) i kopia zapasowa Katalogatora (pliki, których nie ma już
w bibliotece). Potem — głębokie szukanie na dysku nakładką na **Windows File Recovery** (winfr, darmowy program
Microsoftu ze Sklepu): tryb „dokładny” (/extensive) sięga daleko w przeszłość, także po formatowaniu i na kartach
pamięci; „szybki” (/regular) — niedawno usunięte z NTFS. Odzyskane pliki trafiają na INNY dysk niż ten, z którego
odzyskujemy (inaczej nadpisałyby to, co chcemy odzyskać).
"""

from __future__ import annotations

import ntpath
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

WINDOWS = sys.platform == "win32"
ID_SKLEPU = "9N26S50LN705"  # Windows File Recovery w Microsoft Store
FOLDER_WYNIKOW = "Odzyskane przez Katalogator"
SKRYPT, DZIENNIK, KONIEC = ".katalogator-odzysk.cmd", "winfr.log", "koniec.txt"

TYPY = {
    "zdjecia": [".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".bmp", ".tif", ".tiff", ".webp",
                ".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2"],
    "filmy": [".mp4", ".mov", ".avi", ".mkv", ".wmv", ".3gp", ".m4v", ".mts", ".m2ts", ".mpg", ".mpeg", ".webm"],
    "dokumenty": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".txt", ".rtf"],
    "muzyka": [".mp3", ".m4a", ".wav", ".flac", ".wma", ".ogg", ".aac", ".opus"],
    "archiwa": [".zip", ".rar", ".7z", ".tar", ".gz", ".iso"],
    "wszystko": [],
}


def rozszerzenia(typ) -> list[str]:
    """Rodzaj („filmy”) albo wybrane formaty (["mp4", ".MOV"]) → lista rozszerzeń; [] = wszystkie pliki."""
    if isinstance(typ, (list, tuple)):
        wynik = []
        for e in typ:
            e = "." + str(e).strip().lower().lstrip(".*")
            if re.fullmatch(r"\.[a-z0-9]{1,8}", e) and e not in wynik:
                wynik.append(e)
        return wynik[:60]
    return TYPY.get(typ, [])
FOLDERY_UZYTKOWNIKA = [("Pobrane", "Downloads"), ("Pulpit", "Desktop"), ("Dokumenty", "Documents"),
                       ("Obrazy", "Pictures"), ("Wideo", "Videos"), ("Muzyka", "Music")]


def rodzaj_pliku(nazwa: str) -> str:
    e = os.path.splitext(nazwa)[1].lower()
    return next((t for t, r in TYPY.items() if e in r), "inne")


def pasuje(nazwa: str, typ, fraza: str) -> bool:
    r = rozszerzenia(typ)
    if r and os.path.splitext(nazwa)[1].lower() not in r:
        return False
    return not fraza or fraza.lower() in nazwa.lower()


# --- Windows File Recovery ----------------------------------------------------------------------------
def winfr() -> str | None:
    """Ścieżka do winfr.exe (alias aplikacji ze Sklepu w WindowsApps) albo None."""
    p = shutil.which("winfr")
    if p:
        return p
    alias = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "winfr.exe")
    return alias if os.path.exists(alias) else None


def instaluj() -> dict:
    """Instalacja ze Sklepu: winget (bez klikania) albo strona programu w Microsoft Store."""
    if not WINDOWS:
        return {"blad": "Windows File Recovery działa tylko w Windows 10/11."}
    wg = shutil.which("winget")
    if wg:
        subprocess.Popen([wg, "install", "--id", ID_SKLEPU, "--source", "msstore", "--accept-package-agreements",
                          "--accept-source-agreements", "--silent"], creationflags=0x08000000)  # bez okna
        return {"ok": True, "sposob": "winget"}
    os.startfile(f"ms-windows-store://pdp/?productid={ID_SKLEPU}")  # noqa: S606
    return {"ok": True, "sposob": "sklep"}


def podziel(sciezka: str) -> tuple[str, str]:
    """„C:\\Users\\Ja\\Downloads” → („C:”, „\\Users\\Ja\\Downloads\\”); sam dysk → („C:”, „”)."""
    sciezka = ntpath.normpath(sciezka)  # zawsze ścieżki Windows (winfr)
    dysk, reszta = ntpath.splitdrive(sciezka)
    reszta = reszta.replace("/", "\\").strip("\\")
    return dysk.upper(), ("\\" + reszta + "\\") if reszta else ""


def wzorce(folder: str, typ, fraza: str) -> list[str]:
    """Filtry /n dla winfr: folder (względem dysku) × rozszerzenia × fragment nazwy."""
    fraza = re.sub(r'[\\/:"<>|?*%^&]+', "", fraza or "").strip()  # bez znaków specjalnych ścieżek i cmd
    rozsz = rozszerzenia(typ) or [""]
    if not fraza and not rozsz[0]:
        return [folder] if folder else []
    return [f"{folder}*{fraza}*{e}" if fraza else f"{folder}*{e}" for e in rozsz]


def polecenie(exe: str, dysk: str, cel: str, dokladnie: bool, filtry: list[str]) -> list[str]:
    args = [exe, dysk, cel, "/extensive" if dokladnie else "/regular"]
    for f in filtry:
        args += ["/n", f]
    return args + ["/a"]  # bez pytań „Kontynuować? (y/n)”


def _cmd(args: list[str]) -> str:
    return " ".join(f'"{a}"' if (" " in a or not a) else a for a in args)


def folder_wynikow(cel: str) -> str:
    """Sam dysk („E:\\”) → E:\\Odzyskane przez Katalogator; wybrany folder — dokładnie ten folder."""
    cel = ntpath.normpath(cel or "")
    d, reszta = ntpath.splitdrive(cel)
    return ntpath.join(d + "\\", FOLDER_WYNIKOW) if reszta.strip("\\") == "" else cel


def uruchom(dysk: str, cel_miejsce: str, folder: str, typ, fraza: str, dokladnie: bool) -> dict:
    """Start winfr z uprawnieniami administratora (Windows zapyta o zgodę). Okno winfr — zminimalizowane;
    zamknięcie go przerywa szukanie. `cel_miejsce` — dysk albo folder na odzyskane pliki (na innym dysku)."""
    exe = winfr()
    if not exe:
        return {"blad": "Najpierw zainstaluj Windows File Recovery (przycisk wyżej)."}
    if not dysk or not cel_miejsce or dysk[:1].upper() == cel_miejsce[:1].upper():
        return {"blad": "Odzyskane pliki muszą trafić na INNY dysk niż ten, na którym ich szukasz — "
                        "inaczej nadpisałyby to, co chcemy odzyskać. Podłącz pendrive lub dysk USB."}
    cel = folder_wynikow(cel_miejsce)
    os.makedirs(cel, exist_ok=True)
    for n in (DZIENNIK, KONIEC):
        try:
            os.remove(os.path.join(cel, n))
        except OSError:
            pass
    args = polecenie(exe, dysk[:2], cel, dokladnie, wzorce(folder, typ, fraza))
    skrypt = os.path.join(cel, SKRYPT)
    with open(skrypt, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("@echo off\nchcp 65001 >nul\ntitle Katalogator - odzyskiwanie (zamknij, aby przerwac)\n")
        f.write(f'{_cmd(args).replace("%", "%%")} > "{os.path.join(cel, DZIENNIK)}" 2>&1\n')
        f.write(f'echo %errorlevel% > "{os.path.join(cel, KONIEC)}"\n')
    if not WINDOWS:
        return {"blad": "Windows File Recovery działa tylko w Windows 10/11."}
    import ctypes
    w = ctypes.windll.shell32.ShellExecuteW(None, "runas", os.environ.get("ComSpec", "cmd.exe"),
                                            f'/c "{skrypt}"', cel, 7)  # 7 = zminimalizowane, bez fokusu
    if w <= 32:
        return {"blad": "Windows nie pozwolił uruchomić odzyskiwania (potrzebna zgoda administratora — "
                        "kliknij „Tak” w okienku Windows)."}
    return {"ok": True, "cel": cel, "start": time.time(), "polecenie": _cmd(args[1:])}


def _czytaj(sciezka: str) -> str:
    try:
        with open(sciezka, "rb") as f:
            d = f.read()
    except OSError:
        return ""
    if d[:2] in (b"\xff\xfe", b"\xfe\xff") or d[1:200:2].count(b"\0") > 50:
        return d.decode("utf-16", errors="replace")
    for kod in ("utf-8", "cp852", "cp1250"):
        try:
            return d.decode(kod)
        except UnicodeDecodeError:
            continue
    return d.decode("utf-8", errors="replace")


def postep(zadanie: dict | None) -> dict | None:
    """Stan trwającego / zakończonego odzyskiwania z dziennika winfr (procent, ostatni komunikat)."""
    if not zadanie or not zadanie.get("cel"):
        return None
    cel = zadanie["cel"]
    log = _czytaj(os.path.join(cel, DZIENNIK))
    linie = [x.strip() for x in re.split(r"[\r\n]+", log) if x.strip()]
    procent = None
    for m in re.finditer(r"(\d{1,3})\s*%", log):
        procent = min(100, int(m.group(1)))
    koniec = _czytaj(os.path.join(cel, KONIEC)).strip()
    kod = int(koniec) if koniec.lstrip("-").isdigit() else None
    return {**zadanie, "procent": procent, "komunikat": linie[-1][:300] if linie else "",
            "dziennik": "\n".join(linie[-12:]), "zakonczone": kod is not None, "kod": kod,
            "znalezione": len(_pliki_wynikow(cel, zadanie.get("start", 0), limit=100000))}


def _foldery_wynikow(cel: str, start: float) -> list[str]:
    """Foldery Recovery_<data> utworzone przez winfr w tym (albo późniejszym) odzyskiwaniu."""
    try:
        return [w.path for w in os.scandir(cel) if w.is_dir() and w.name.lower().startswith("recovery_")
                and w.stat().st_mtime >= start - 120]
    except OSError:
        return []


def _pliki_wynikow(cel: str, start: float, limit: int = 20000) -> list[tuple[str, str, os.stat_result]]:
    wynik = []
    for f in _foldery_wynikow(cel, start):
        for katalog, _, pliki in os.walk(f):
            for n in pliki:
                if n.lower() in ("recoverylog.txt",):
                    continue
                p = os.path.join(katalog, n)
                try:
                    wynik.append((p, os.path.relpath(p, f), os.stat(p)))
                except OSError:
                    continue
                if len(wynik) >= limit:
                    return wynik
    return wynik


def wyniki(zadanie: dict | None, typ="wszystko", fraza: str = "", min_kb: int = 0,
           od: int = 0, ile: int = 200) -> dict:
    if not zadanie or not zadanie.get("cel"):
        return {"razem": 0, "pliki": []}
    lista = [(p, rel, st) for p, rel, st in _pliki_wynikow(zadanie["cel"], zadanie.get("start", 0))
             if pasuje(os.path.basename(p), typ, fraza) and st.st_size >= min_kb * 1024]
    lista.sort(key=lambda x: (rodzaj_pliku(x[0]) == "inne", -x[2].st_size))
    return {"razem": len(lista), "folder": zadanie["cel"],
            "pliki": [{"sciezka": p, "nazwa": os.path.basename(p), "gdzie": os.path.dirname(rel),
                       "rozmiar": st.st_size, "rodzaj": rodzaj_pliku(p),
                       "data": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")}
                      for p, rel, st in lista[od:od + ile]]}


def w_wynikach(zadanie: dict | None, sciezka: str) -> bool:
    """Miniatury / otwieranie tylko dla plików z folderu odzyskanych."""
    if not zadanie or not zadanie.get("cel") or not sciezka:
        return False
    a, b = os.path.normcase(os.path.realpath(sciezka)), os.path.normcase(os.path.realpath(zadanie["cel"]))
    return a.startswith(b.rstrip("\\/") + os.sep) and os.path.isfile(sciezka)


# --- kosze Windows ($Recycle.Bin): także na innych dyskach ---------------------------------------------
def czytaj_i(dane: bytes) -> dict | None:
    """Plik $I… z kosza Windows: oryginalna ścieżka, rozmiar, czas usunięcia (wersja 1: Vista–8, 2: 10/11)."""
    if len(dane) < 24:
        return None
    wersja, rozmiar, ft = struct.unpack_from("<qqq", dane, 0)
    try:
        if wersja == 2 and len(dane) >= 28:
            n = struct.unpack_from("<i", dane, 24)[0]
            nazwa = dane[28:28 + 2 * n].decode("utf-16-le", errors="replace")
        elif wersja == 1:
            nazwa = dane[24:24 + 520].decode("utf-16-le", errors="replace")
        else:
            return None
    except struct.error:
        return None
    kiedy = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=ft // 10) if ft > 0 else None
    return {"oryginal": nazwa.split("\0", 1)[0], "rozmiar": rozmiar,
            "usuniety": kiedy.astimezone().replace(tzinfo=None).isoformat(timespec="seconds") if kiedy else None}


def _kosze(dyski: list[str]) -> list[str]:
    wynik = []
    for d in dyski:
        k = os.path.join(d, "$Recycle.Bin")
        try:
            for w in os.scandir(k):  # podfolder dla każdego użytkownika (SID); cudze — brak dostępu
                if w.is_dir():
                    wynik.append(w.path)
        except OSError:
            continue
    return wynik


def kosze_windows(dyski: list[str], typ, fraza: str, limit: int = 500) -> list[dict]:
    wynik = []
    for k in _kosze(dyski):
        try:
            wpisy = list(os.scandir(k))
        except OSError:
            continue
        for w in wpisy:
            if not w.name.upper().startswith("$I"):
                continue
            try:
                with open(w.path, "rb") as f:
                    info = czytaj_i(f.read(4096))
            except OSError:
                continue
            r = os.path.join(k, "$R" + w.name[2:])
            if not info or not os.path.exists(r):
                continue
            nazwa = os.path.basename(info["oryginal"])
            if os.path.isdir(r):  # usunięty cały folder — szukamy w środku
                for katalog, _, pliki in os.walk(r):
                    for n in pliki:
                        if pasuje(n, typ, fraza):
                            p = os.path.join(katalog, n)
                            wynik.append({"zrodlo": "kosz_windows", "sciezka": p, "nazwa": n,
                                          "oryginal": os.path.join(info["oryginal"], os.path.relpath(p, r)),
                                          "rozmiar": os.path.getsize(p), "usuniety": info["usuniety"],
                                          "rodzaj": rodzaj_pliku(n)})
            elif pasuje(nazwa, typ, fraza):
                wynik.append({"zrodlo": "kosz_windows", "sciezka": r, "nazwa": nazwa, "oryginal": info["oryginal"],
                              "rozmiar": info["rozmiar"], "usuniety": info["usuniety"], "rodzaj": rodzaj_pliku(nazwa)})
            if len(wynik) >= limit:
                return wynik
    return sorted(wynik, key=lambda x: x["usuniety"] or "", reverse=True)


# --- kosz programu i kopia zapasowa --------------------------------------------------------------------
def kosz_programu(korzenie: list[str], typ, fraza: str, limit: int = 500) -> list[dict]:
    from .duplikaty import FOLDER_ODLOZONE
    wynik = []
    for k in dict.fromkeys(korzenie):
        o = os.path.join(k, FOLDER_ODLOZONE)
        for katalog, _, pliki in os.walk(o):
            for n in pliki:
                if pasuje(n, typ, fraza):
                    p = os.path.join(katalog, n)
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                    wynik.append({"zrodlo": "kosz_programu", "sciezka": p, "nazwa": n, "oryginal": "",
                                  "rozmiar": st.st_size, "rodzaj": rodzaj_pliku(n), "gdzie": os.path.relpath(katalog, o),
                                  "usuniety": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
                    if len(wynik) >= limit:
                        return wynik
    return wynik


def z_kopii(biblioteka: str, kopia_folder: str, typ, fraza: str, limit: int = 500, czas: float = 120) -> dict:
    """Pliki, które są w kopii zapasowej, a których nie ma już w bibliotece (usunięte — kopia nic nie kasuje)."""
    if not biblioteka or not kopia_folder or not os.path.isdir(kopia_folder) or not os.path.isdir(biblioteka):
        return {"pliki": [], "przerwane": False}
    from .duplikaty import FOLDER_ODLOZONE
    wynik, t0 = [], time.monotonic()
    for katalog, foldery, pliki in os.walk(kopia_folder):
        if katalog == kopia_folder and FOLDER_ODLOZONE in foldery:
            foldery.remove(FOLDER_ODLOZONE)
        rel_k = os.path.relpath(katalog, kopia_folder)
        cel_k = os.path.normpath(os.path.join(biblioteka, rel_k))
        istniejace = None
        for n in pliki:
            if not pasuje(n, typ, fraza) or ".katalogator-tmp" in n:
                continue
            if istniejace is None:  # jeden odczyt folderu biblioteki zamiast sprawdzania pliku po pliku
                try:
                    istniejace = {x.lower() for x in os.listdir(cel_k)}
                except OSError:
                    istniejace = set()
            if n.lower() in istniejace:
                continue
            p = os.path.join(katalog, n)
            try:
                st = os.stat(p)
            except OSError:
                continue
            wynik.append({"zrodlo": "kopia", "sciezka": p, "nazwa": n, "oryginal": os.path.join(cel_k, n),
                          "rozmiar": st.st_size, "rodzaj": rodzaj_pliku(n),
                          "usuniety": None, "data": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
            if len(wynik) >= limit:
                return {"pliki": wynik, "przerwane": True}
        if time.monotonic() - t0 > czas:
            return {"pliki": wynik, "przerwane": True}
    return {"pliki": wynik, "przerwane": False}


def _wolna(sciezka: str) -> str:
    if not os.path.exists(sciezka):
        return sciezka
    rdzen, rozsz = os.path.splitext(sciezka)
    i = 1
    while True:
        p = f"{rdzen} (odzyskane{'' if i == 1 else f' {i}'}){rozsz}"
        if not os.path.exists(p):
            return p
        i += 1


def przywroc(element: dict, dozwolone: dict, do_folderu: str | None = None) -> dict:
    """Kosz Windows: przeniesienie na oryginalne miejsce. Kopia: skopiowanie z powrotem do biblioteki.
    `do_folderu` — zamiast oryginalnego miejsca: wybrany folder (ta sama nazwa pliku).
    `dozwolone` — {"kosze": [...], "kopia": folder} — przywracamy tylko z tych miejsc."""
    zr, sc, orig = element.get("zrodlo"), element.get("sciezka") or "", element.get("oryginal") or ""
    if do_folderu:
        if not os.path.isdir(do_folderu):
            return {"blad": "Nie ma takiego folderu — wybierz inny."}
        orig = os.path.join(do_folderu, element.get("nazwa") or os.path.basename(orig.replace("\\", "/")) or "plik")

    def wewnatrz(p, katalogi):
        p = os.path.normcase(os.path.realpath(p))
        return any(p.startswith(os.path.normcase(os.path.realpath(k)).rstrip("\\/") + os.sep) for k in katalogi if k)
    if zr == "kosz_windows" and wewnatrz(sc, dozwolone.get("kosze") or []) and orig:
        cel = _wolna(orig)
        os.makedirs(os.path.dirname(cel), exist_ok=True)
        shutil.move(sc, cel)
        i = os.path.join(os.path.dirname(sc), "$I" + os.path.basename(sc)[2:])
        if os.path.basename(sc).upper().startswith("$R") and os.path.exists(i):
            try:
                os.remove(i)
            except OSError:
                pass
        return {"ok": True, "sciezka": cel}
    if zr == "kopia" and wewnatrz(sc, [dozwolone.get("kopia")]) and orig:
        cel = _wolna(orig)
        os.makedirs(os.path.dirname(cel), exist_ok=True)
        shutil.copy2(sc, cel)
        return {"ok": True, "sciezka": cel}
    return {"blad": "Tego pliku nie da się przywrócić stąd."}


# --- dysk SSD? (po usunięciu z SSD szanse maleją z minuty na minutę — TRIM) --------------------------------
_SSD: dict[str, bool | None] = {}


def ssd(litera: str) -> bool | None:
    litera = (litera or "")[:1].upper()
    if not WINDOWS or not litera:
        return None
    if litera not in _SSD:
        try:
            w = subprocess.run(["powershell", "-NoProfile", "-Command",
                                f"(Get-Partition -DriveLetter {litera} | Get-Disk | Get-PhysicalDisk).MediaType"],
                               capture_output=True, text=True, timeout=8, creationflags=0x08000000)
            t = w.stdout.strip().upper()
            _SSD[litera] = True if "SSD" in t else False if "HDD" in t else None
        except (OSError, subprocess.SubprocessError):
            _SSD[litera] = None
    return _SSD[litera]


def foldery_uzytkownika() -> list[dict]:
    dom = os.path.expanduser("~")
    return [{"nazwa": n, "sciezka": os.path.join(dom, k)} for n, k in FOLDERY_UZYTKOWNIKA
            if os.path.isdir(os.path.join(dom, k))]
