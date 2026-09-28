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

def _stopnie(wart, ref) -> float | None:
    try:
        st, mi, se = (float(x) for x in wart)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    w = st + mi / 60 + se / 3600
    if isinstance(ref, bytes):
        ref = ref.decode(errors="ignore")
    if str(ref).strip().upper() in ("S", "W"):
        w = -w
    return w


def z_obrazu(sciezka: str, m: Metadane) -> None:
    if Image is None:
        return
    with Image.open(sciezka) as im:  # leniwe: czyta tylko nagłówek
        exif = im.getexif()
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
    marka = str(exif.get(0x010F) or "").strip("\x00 ")
    model = str(exif.get(0x0110) or "").strip("\x00 ")
    if model:
        m.aparat = model if model.lower().startswith(marka.lower()) else f"{marka} {model}".strip()
    gps = exif.get_ifd(0x8825)
    if gps and 2 in gps and 4 in gps:
        lat, lon = _stopnie(gps[2], gps.get(1, "N")), _stopnie(gps[4], gps.get(3, "E"))
        if lat is not None and lon is not None and (abs(lat) > 1e-6 or abs(lon) > 1e-6):
            m.lat, m.lon = round(lat, 6), round(lon, 6)


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


def odczytaj(sciezka: str, rodzaj: str, mtime: float) -> Metadane:
    m = Metadane()
    ext = PurePath(sciezka).suffix.lower()
    try:
        if rodzaj == typy.ZDJECIE:
            z_obrazu(sciezka, m)
        elif rodzaj == typy.FILM and ext in _MP4_PODOBNE:
            z_mp4(sciezka, m)
        elif rodzaj == typy.MUZYKA_:
            z_muzyki(sciezka, m)
    except Exception as e:  # uszkodzony / nietypowy plik — nie przerywa skanu
        m.blad = f"{type(e).__name__}: {e}"[:200]
    if rodzaj in (typy.ZDJECIE, typy.FILM) and m.data is None:
        d = data_z_nazwy(sciezka)
        if d:
            m.data, m.zrodlo_daty = d, "nazwa"
        else:
            m.data, m.zrodlo_daty = datetime.fromtimestamp(mtime), "plik"
    return m
