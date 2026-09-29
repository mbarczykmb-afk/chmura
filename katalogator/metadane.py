"""Odczyt daty, GPS i tagów z nagłówków plików (bez czytania całej zawartości)."""

from __future__ import annotations

import io
import re
import struct
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import PurePath

from . import typy

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

try:  # zdjęcia HEIC z telefonów (opcjonalnie)
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

try:
    import mutagen
except ImportError:  # pragma: no cover
    mutagen = None


@dataclass
class Metadane:
    data: datetime | None = None
    zrodlo_daty: str | None = None  # exif | film | nazwa | plik
    lat: float | None = None
    lon: float | None = None
    aparat: str | None = None
    wykonawca: str | None = None
    album: str | None = None
    tytul: str | None = None
    blad: str | None = None


ROK_MIN = 1990

# 20230714_153012, IMG_20230714_153012, PXL_20230714_153012345, Screenshot_2023-07-14-15-30-12
_DATA_CZAS = re.compile(
    r"(?<!\d)((?:19|20)\d{2})[-_.]?(\d{2})[-_.]?(\d{2})[-_ T.]?(\d{2})[-_.:]?(\d{2})[-_.:]?(\d{2})"
)
# IMG-20230714-WA0001, 2023-07-14
_DATA = re.compile(r"(?<!\d)((?:19|20)\d{2})[-_.]?(\d{2})[-_.]?(\d{2})(?!\d)")


def _poprawna(*czesci: int) -> datetime | None:
    try:
        d = datetime(*czesci)
    except ValueError:
        return None
    if not (ROK_MIN <= d.year <= datetime.now().year + 1):
        return None
    return d


def data_z_nazwy(nazwa: str) -> datetime | None:
    stem = PurePath(nazwa).stem
    for wzor in (_DATA_CZAS, _DATA):
        for m in wzor.finditer(stem):
            d = _poprawna(*(int(x) for x in m.groups()))
            if d:
                return d
    return None


# --- zdjęcia -------------------------------------------------------------

def _aparat(marka, model) -> str | None:
    marka, model = str(marka or "").strip("\x00 "), str(model or "").strip("\x00 ")
    if not model:
        return None
    pierwsze = marka.split(" ")[0].lower()
    if pierwsze and model.lower().startswith(pierwsze):
        return model  # „NIKON D750” zamiast „NIKON CORPORATION NIKON D750”
    return f"{marka} {model}".strip()


def _stopnie(wart, ref) -> float | None:
    """Stopnie z EXIF: (st, min, sek), (st, min) albo same stopnie; bez NaN (ułamki 0/0 z niektórych aparatów)."""
    try:
        cz = [float(x) for x in (wart if isinstance(wart, (tuple, list)) else (wart,))]
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    cz = (cz + [0.0, 0.0])[:3]
    if any(c != c or c in (float("inf"), float("-inf")) for c in cz):
        return None
    w = cz[0] + cz[1] / 60 + cz[2] / 3600
    if isinstance(ref, bytes):
        ref = ref.decode(errors="ignore")
    if str(ref).strip().upper() in ("S", "W"):
        w = -w
    return w


def _ustaw_gps(m: Metadane, lat, lon) -> bool:
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    if abs(lat) <= 90 and abs(lon) <= 180 and (abs(lat) > 1e-6 or abs(lon) > 1e-6) and lat == lat and lon == lon:
        m.lat, m.lon = round(lat, 6), round(lon, 6)
        return True
    return False


# XMP: exif:GPSLatitude="50,16.8667N" / "50,16,52N" / <exif:GPSLatitude>…</…>, drony: drone-dji:GpsLatitude="+50.1"
_XMP_GPS = re.compile(rb'(?:exif:GPS|drone-dji:Gps)(Latitude|Longitude)(?:="|>)\s*([+-]?[\d.]+(?:,[\d.]+){0,2})\s*([NSEW]?)', re.I)
_XMP_DATA = re.compile(rb'(?:exif:DateTimeOriginal|photoshop:DateCreated|xmp:CreateDate)(?:="|>)\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?)')


def z_xmp(dane: bytes, m: Metadane) -> None:
    """GPS i data z pakietu XMP (Lightroom, Photoshop, Google Zdjęcia, drony, pliki .xmp obok zdjęcia)."""
    if not dane:
        return
    if m.lat is None:
        wsp = {}
        for os_, wart, ref in _XMP_GPS.findall(dane[:2_000_000]):
            cz = [float(x) for x in wart.decode().split(",")]
            w = cz[0] + (cz[1] / 60 if len(cz) > 1 else 0) + (cz[2] / 3600 if len(cz) > 2 else 0)
            if ref.upper() in (b"S", b"W"):
                w = -w
            wsp.setdefault(os_.decode().lower(), w)
        if "latitude" in wsp and "longitude" in wsp:
            _ustaw_gps(m, wsp["latitude"], wsp["longitude"])
    if m.zrodlo_daty != "exif":
        d = _XMP_DATA.search(dane[:2_000_000])
        if d:
            try:
                dt = datetime.fromisoformat(d.group(1).decode())
                if dt.year >= ROK_MIN:
                    m.data, m.zrodlo_daty = dt, "exif"
            except ValueError:
                pass


def z_takeout(dane: bytes, m: Metadane) -> None:
    """Plik .json z eksportu Google Zdjęć (Takeout): geoData / geoDataExif, photoTakenTime."""
    import json
    try:
        j = json.loads(dane.decode("utf-8", errors="replace"))
    except ValueError:
        return
    if not isinstance(j, dict):
        return
    if m.lat is None:
        for k in ("geoDataExif", "geoData"):
            g = j.get(k) or {}
            if isinstance(g, dict) and _ustaw_gps(m, g.get("latitude"), g.get("longitude")):
                break
    if m.zrodlo_daty != "exif":
        t = (j.get("photoTakenTime") or {}).get("timestamp") if isinstance(j.get("photoTakenTime"), dict) else None
        try:
            dt = datetime.fromtimestamp(int(t)) if t else None
        except (ValueError, OSError, OverflowError):
            dt = None
        if dt and dt.year >= ROK_MIN:
            m.data, m.zrodlo_daty = dt, "exif"


def z_bocznych(sciezki: list[str], m: Metadane) -> None:
    """Pliki towarzyszące leżące obok zdjęcia/filmu: .json (Google), .xmp (Lightroom, darktable…)."""
    for s in sciezki:
        if m.lat is not None and m.zrodlo_daty == "exif":
            return
        try:
            with open(s, "rb") as f:
                dane = f.read(2_000_000)
        except OSError:
            continue
        (z_takeout if s.lower().endswith(".json") else z_xmp)(dane, m)


def boczne_nazwy(sciezka: str) -> list[str]:
    """Możliwe nazwy plików towarzyszących: IMG_1.jpg.json, IMG_1.jpg.supplemental-metadata.json, IMG_1.json,
    IMG_1.xmp, IMG_1.jpg.xmp (porównywane bez wielkości liter)."""
    rdzen = str(PurePath(sciezka).with_suffix(""))
    return [sciezka + ".json", sciezka + ".supplemental-metadata.json", rdzen + ".json",
            rdzen + ".xmp", sciezka + ".xmp"]


def z_obrazu(sciezka: str, m: Metadane) -> None:
    if Image is None:
        return
    with Image.open(sciezka) as im:  # leniwe: czyta tylko nagłówek
        exif = im.getexif()
        xmp = im.info.get("xmp") or im.info.get("XML:com.adobe.xmp") or b""
    if isinstance(xmp, str):
        xmp = xmp.encode("utf-8", errors="ignore")
    try:
        _z_exif(exif, m)
    finally:
        z_xmp(xmp, m)  # GPS/data dopisane w programie do zdjęć (bez dodatkowego czytania pliku)


def _z_exif(exif, m: Metadane) -> None:
    if not exif:
        return
    ifd = exif.get_ifd(0x8769)
    tekst = ifd.get(36867) or ifd.get(36868) or exif.get(306)
    if tekst:
        try:
            d = datetime.strptime(str(tekst).strip("\x00 ")[:19], "%Y:%m:%d %H:%M:%S")
            if d.year >= ROK_MIN:
                m.data, m.zrodlo_daty = d, "exif"
        except ValueError:
            pass
    m.aparat = _aparat(exif.get(0x010F), exif.get(0x0110))
    gps = exif.get_ifd(0x8825)
    if gps and 2 in gps and 4 in gps:
        lat, lon = _stopnie(gps[2], gps.get(1, "N")), _stopnie(gps[4], gps.get(3, "E"))
        if lat is not None and lon is not None:
            _ustaw_gps(m, lat, lon)


# --- filmy MP4/MOV/3GP ---------------------------------------------------

_EPOKA_MP4 = datetime(1904, 1, 1, tzinfo=timezone.utc)
_ISO6709 = re.compile(rb"([+-]\d{1,2}\.\d{2,})([+-]\d{1,3}\.\d{2,})")
_APPLE_DATA = re.compile(rb"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")
_MAX_MOOV = 64 * 1024 * 1024


def _boxy(f, start: int, koniec: int):
    pos = start
    while pos + 8 <= koniec:
        f.seek(pos)
        naglowek = f.read(8)
        if len(naglowek) < 8:
            return
        rozmiar, typ = struct.unpack(">I4s", naglowek)
        dl = 8
        if rozmiar == 1:
            rozmiar = struct.unpack(">Q", f.read(8))[0]
            dl = 16
        elif rozmiar == 0:
            rozmiar = koniec - pos
        if rozmiar < dl:
            return
        yield typ, pos + dl, pos + rozmiar
        pos += rozmiar


def z_mp4(sciezka: str, m: Metadane) -> None:
    with open(sciezka, "rb") as f:
        f.seek(0, io.SEEK_END)
        koniec = f.tell()
        moov = None
        for typ, s, e in _boxy(f, 0, koniec):
            if typ == b"moov":
                if e - s > _MAX_MOOV:
                    return
                f.seek(s)
                moov = f.read(e - s)
                break
    if not moov:
        return
    b = io.BytesIO(moov)
    for typ, s, e in _boxy(b, 0, len(moov)):
        if typ == b"mvhd":
            wersja = moov[s]
            if wersja == 1:
                sek = struct.unpack(">Q", moov[s + 4:s + 12])[0]
            else:
                sek = struct.unpack(">I", moov[s + 4:s + 8])[0]
            if sek:
                d = (_EPOKA_MP4 + timedelta(seconds=sek)).astimezone().replace(tzinfo=None)
                if d.year >= ROK_MIN:
                    m.data, m.zrodlo_daty = d, "film"
            break
    # Apple: com.apple.quicktime.creationdate (czas lokalny) ma pierwszeństwo
    if b"com.apple.quicktime.creationdate" in moov:
        for kand in _APPLE_DATA.finditer(moov):
            d = _poprawna(*map(int, re.split(rb"[-T:]", kand.group(1))))
            if d:
                m.data, m.zrodlo_daty = d, "film"
                break
    # GPS: ©xyz (Android/Samsung) lub ISO6709 Apple — ten sam zapis tekstowy
    gps = None
    i = moov.find(b"\xa9xyz")
    if i >= 0:
        gps = _ISO6709.search(moov, i, i + 200)
    elif b"location.ISO6709" in moov:
        gps = _ISO6709.search(moov)
    if gps:
        lat, lon = float(gps.group(1)), float(gps.group(2))
        if abs(lat) <= 90 and abs(lon) <= 180 and (lat or lon):
            m.lat, m.lon = round(lat, 6), round(lon, 6)



# --- RAW (TIFF: DNG, CR2, NEF, ARW, ORF, RW2, PEF, SRW) ---------------------------

_TIFF_RAW = {".dng", ".cr2", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".orf", ".rw2", ".pef", ".srw", ".tif", ".tiff",
             ".raf", ".cr3"}
_ROZM_TYPU = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}


def _ifd(f, poz: int, bo: str) -> dict:
    """Wpisy IFD: tag -> (typ, liczba, surowe 4 bajty wartości/przesunięcia)."""
    f.seek(poz)
    n = struct.unpack(bo + "H", f.read(2))[0]
    if n > 1000:
        raise ValueError("uszkodzony IFD")
    wpisy = {}
    for _ in range(n):
        tag, typ, licz = struct.unpack(bo + "HHI", f.read(8))
        wpisy[tag] = (typ, licz, f.read(4))
    return wpisy


def _wartosc(f, wpis, bo: str, baza: int = 0):
    typ, licz, surowe = wpis
    rozm = _ROZM_TYPU.get(typ, 1) * licz
    if rozm <= 4:
        dane = surowe[:rozm]
    else:
        f.seek(baza + struct.unpack(bo + "I", surowe)[0])
        dane = f.read(min(rozm, 4096))
    if typ == 2:
        return dane.split(b"\0", 1)[0].decode("latin-1", "ignore").strip()
    if typ == 3:
        return struct.unpack(bo + "H" * licz, dane[:2 * licz])
    if typ == 4:
        return struct.unpack(bo + "I" * licz, dane[:4 * licz])
    if typ in (5, 10):
        wart = struct.unpack(bo + ("I" if typ == 5 else "i") * (2 * licz), dane[:8 * licz])
        return tuple(wart[i] / wart[i + 1] if wart[i + 1] else 0 for i in range(0, len(wart), 2))
    return dane


def z_tiff(sciezka: str, m: Metadane) -> None:
    """Data, aparat i GPS z nagłówka TIFF — działa dla większości plików RAW."""
    with open(sciezka, "rb") as f:
        naglowek = f.read(16)
        baza = 0
        if naglowek[:8] == b"FUJIFILM":  # RAF: wbudowany JPEG z EXIF
            f.seek(84)
            off = struct.unpack(">I", f.read(4))[0]
            f.seek(off)
            jpg = f.read(256 * 1024)
            if Image is not None:
                with Image.open(io.BytesIO(jpg)) as im:
                    ex = im.getexif()
                t = ex.get_ifd(0x8769).get(36867) or ex.get(306)
                if t:
                    _ustaw_date(m, str(t))
            return
        if naglowek[:2] not in (b"II", b"MM"):
            return
        bo = "<" if naglowek[:2] == b"II" else ">"
        ifd0 = struct.unpack(bo + "I", naglowek[4:8])[0]
        w = _ifd(f, baza + ifd0, bo)
        marka = _wartosc(f, w[0x010F], bo) if 0x010F in w else ""
        model = _wartosc(f, w[0x0110], bo) if 0x0110 in w else ""
        m.aparat = _aparat(marka, model)
        tekst = None
        if 0x8769 in w:
            ex = _ifd(f, baza + _wartosc(f, w[0x8769], bo)[0], bo)
            for tag in (36867, 36868):
                if tag in ex:
                    tekst = _wartosc(f, ex[tag], bo)
                    break
        if not tekst and 0x0132 in w:
            tekst = _wartosc(f, w[0x0132], bo)
        if tekst:
            _ustaw_date(m, tekst)
        if 0x8825 in w:
            g = _ifd(f, baza + _wartosc(f, w[0x8825], bo)[0], bo)
            if 2 in g and 4 in g:
                lat = _stopnie(_wartosc(f, g[2], bo), _wartosc(f, g[1], bo) if 1 in g else "N")
                lon = _stopnie(_wartosc(f, g[4], bo), _wartosc(f, g[3], bo) if 3 in g else "E")
                if lat is not None and lon is not None and (abs(lat) > 1e-6 or abs(lon) > 1e-6):
                    m.lat, m.lon = round(lat, 6), round(lon, 6)


def _ustaw_date(m: Metadane, tekst: str) -> None:
    try:
        d = datetime.strptime(str(tekst).strip("\x00 ")[:19], "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return
    if d.year >= ROK_MIN:
        m.data, m.zrodlo_daty = d, "exif"


# --- AVI (RIFF: IDIT / ICRD) i MKV/WebM (EBML: DateUTC) ------------------------------

_MIESIACE_EN = {n: i for i, n in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT",
                                             "NOV", "DEC"], 1)}


def z_avi(sciezka: str, m: Metadane) -> None:
    with open(sciezka, "rb") as f:
        glowa = f.read(256 * 1024)
    if glowa[:4] != b"RIFF":
        return
    for znacznik in (b"IDIT", b"ICRD"):
        i = glowa.find(znacznik)
        if i < 0:
            continue
        dl = struct.unpack("<I", glowa[i + 4:i + 8])[0]
        tekst = glowa[i + 8:i + 8 + min(dl, 64)].split(b"\0")[0].decode("latin-1", "ignore").strip()
        # „THU OCT 26 16:46:04 2006” albo „2006:10:26 16:46:04” / „2006-10-26”
        r = re.match(r"\w{3}\s+(\w{3})\s+(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})\s+(\d{4})", tekst.upper())
        d = None
        if r and r.group(1) in _MIESIACE_EN:
            d = _poprawna(int(r.group(6)), _MIESIACE_EN[r.group(1)], int(r.group(2)),
                          int(r.group(3)), int(r.group(4)), int(r.group(5)))
        else:
            r = re.match(r"(\d{4})[:\-/](\d{2})[:\-/](\d{2})(?:[ T](\d{2}):(\d{2}):(\d{2}))?", tekst)
            if r:
                d = _poprawna(*(int(x) for x in r.groups() if x is not None))
        if d:
            m.data, m.zrodlo_daty = d, "film"
            return


def _ebml_liczba(f, dlugosc_id=False) -> tuple[int, int] | None:
    b = f.read(1)
    if not b:
        return None
    pierwszy = b[0]
    dl = 1
    maska = 0x80
    while dl <= 8 and not (pierwszy & maska):
        maska >>= 1
        dl += 1
    if dl > 8:
        return None
    wart = pierwszy if dlugosc_id else pierwszy & (maska - 1)
    for x in f.read(dl - 1):
        wart = (wart << 8) | x
    return wart, dl


def z_mkv(sciezka: str, m: Metadane) -> None:
    """EBML: Segment (0x18538067) → Info (0x1549A966) → DateUTC (0x4461, ns od 2001-01-01)."""
    with open(sciezka, "rb") as f:
        dane = io.BytesIO(f.read(512 * 1024))

    def elementy(koniec):
        while dane.tell() < koniec:
            e_id = _ebml_liczba(dane, True)
            e_dl = _ebml_liczba(dane)
            if not e_id or not e_dl:
                return
            start = dane.tell()
            yield e_id[0], start, e_dl[0]
            dane.seek(start + e_dl[0])

    naglowek = dane.getbuffer().nbytes
    for eid, start, dl in elementy(naglowek):
        if eid == 0x18538067:  # Segment (często nieznanej długości)
            dane.seek(start)
            for eid2, s2, dl2 in elementy(min(naglowek, start + dl)):
                if eid2 == 0x1549A966:  # Info
                    dane.seek(s2)
                    for eid3, s3, dl3 in elementy(s2 + dl2):
                        if eid3 == 0x4461 and dl3 == 8:
                            dane.seek(s3)
                            ns = struct.unpack(">q", dane.read(8))[0]
                            d = (datetime(2001, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=ns // 1000))
                            d = d.astimezone().replace(tzinfo=None)
                            if d.year >= ROK_MIN:
                                m.data, m.zrodlo_daty = d, "film"
                            return
                    return
            return

# --- muzyka --------------------------------------------------------------

def z_muzyki(sciezka: str, m: Metadane) -> None:
    if mutagen is None:
        return
    plik = mutagen.File(sciezka, easy=True)
    if not plik or not plik.tags:
        return
    t = plik.tags

    def pierwszy(*klucze):
        for k in klucze:
            w = t.get(k)
            if w and str(w[0]).strip():
                return str(w[0]).strip()
        return None

    m.wykonawca = pierwszy("albumartist", "artist")
    m.album = pierwszy("album")
    m.tytul = pierwszy("title")


# --- całość --------------------------------------------------------------

_MP4_PODOBNE = {".mp4", ".mov", ".m4v", ".3gp"}


def odczytaj(sciezka: str, rodzaj: str, mtime: float, boczne: list[str] | None = None) -> Metadane:
    m = Metadane()
    ext = PurePath(sciezka).suffix.lower()
    try:
        if rodzaj == typy.ZDJECIE and ext in _TIFF_RAW:
            z_tiff(sciezka, m)
            if m.data is None and ext == ".cr3":
                z_mp4(sciezka, m)  # CR3 to kontener ISO jak MP4
        elif rodzaj == typy.ZDJECIE:
            z_obrazu(sciezka, m)
        elif rodzaj == typy.FILM and ext in _MP4_PODOBNE:
            z_mp4(sciezka, m)
        elif rodzaj == typy.FILM and ext == ".avi":
            z_avi(sciezka, m)
        elif rodzaj == typy.FILM and ext in (".mkv", ".webm"):
            z_mkv(sciezka, m)
        elif rodzaj == typy.MUZYKA_:
            z_muzyki(sciezka, m)
    except Exception as e:  # uszkodzony / nietypowy plik — nie przerywa skanu
        m.blad = f"{type(e).__name__}: {e}"[:200]
    if boczne and rodzaj in (typy.ZDJECIE, typy.FILM):
        try:
            z_bocznych(boczne, m)
        except Exception:
            pass
    if rodzaj in (typy.ZDJECIE, typy.FILM) and m.data is None:
        d = data_z_nazwy(sciezka)
        if d:
            m.data, m.zrodlo_daty = d, "nazwa"
        else:
            m.data, m.zrodlo_daty = datetime.fromtimestamp(mtime), "plik"
    return m
