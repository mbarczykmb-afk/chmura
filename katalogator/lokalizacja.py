"""📍 Lokalizacja zdjęć i filmów: dodawanie, zmiana (np. przesunięcie pinezki) i usuwanie.

- JPEG: GPS zapisywany w EXIF samego pliku — bez ponownego kodowania obrazu (podmieniamy tylko segment EXIF),
  przez plik tymczasowy i podmianę; data modyfikacji pliku zostaje ta sama. Widzą to inne programy (Windows,
  Google Zdjęcia, telefony).
- Pozostałe (HEIC, PNG, RAW, filmy): plik `<nazwa>.xmp` obok (format Lightroom / darktable / digiKam) —
  oryginał nie jest ruszany. Znacznik `katalogator:Lokalizacja` sprawia, że przy skanie ten plik ma pierwszeństwo
  przed GPS zapisanym w samym pliku („brak” = lokalizacja usunięta).
"""

from __future__ import annotations

import os
import sqlite3

from . import indeks

ZNACZNIK = b"katalogator:Lokalizacja"
_JPEG = (".jpg", ".jpeg", ".jfif")


def _dms(w: float) -> tuple[float, float, float]:
    w = abs(w)
    st = int(w)
    m = int((w - st) * 60)
    s = round(((w - st) * 60 - m) * 60, 4)
    return float(st), float(m), s


def _segmenty(dane: bytes):
    """(początek, koniec, znacznik) segmentów JPEG przed danymi obrazu."""
    if dane[:2] != b"\xff\xd8":
        raise ValueError("to nie jest prawidłowy plik JPEG")
    i = 2
    while i + 4 <= len(dane):
        if dane[i] != 0xFF:
            raise ValueError("uszkodzona struktura JPEG")
        while dane[i + 1] == 0xFF:  # bajty wypełnienia
            i += 1
        znak = dane[i + 1]
        if znak in (0xDA, 0xD9):  # początek danych obrazu / koniec
            return
        if 0xD0 <= znak <= 0xD7 or znak == 0x01:
            i += 2
            continue
        dl = int.from_bytes(dane[i + 2:i + 4], "big")
        yield i, i + 2 + dl, znak
        i += 2 + dl


def _jpeg_z_nowym_exif(dane: bytes, exif: bytes) -> bytes:
    if len(exif) + 2 > 65535:
        raise ValueError("dane EXIF są za duże")
    nowy = b"\xff\xe1" + (len(exif) + 2).to_bytes(2, "big") + exif
    wstaw = 2
    for p, k, znak in _segmenty(dane):
        if znak == 0xE1 and dane[p + 4:p + 10] == b"Exif\x00\x00":
            return dane[:p] + nowy + dane[k:]
        if znak == 0xE0 and p == 2:  # po nagłówku JFIF
            wstaw = k
    return dane[:wstaw] + nowy + dane[wstaw:]


def _zapisz_jpeg(sciezka: str, lat: float | None, lon: float | None) -> None:
    from PIL import Image
    with open(sciezka, "rb") as f:
        dane = f.read()
    with Image.open(sciezka) as im:
        exif = im.getexif()
    gps = exif.get_ifd(0x8825)
    gps.clear()
    if lat is None:
        exif.pop(0x8825, None)
    else:
        gps.update({0: b"\x02\x03\x00\x00", 1: "N" if lat >= 0 else "S", 2: _dms(lat),
                    3: "E" if lon >= 0 else "W", 4: _dms(lon)})
    nowe = _jpeg_z_nowym_exif(dane, exif.tobytes())
    st = os.stat(sciezka)
    tmp = os.path.join(os.path.dirname(sciezka), "." + os.path.basename(sciezka) + ".katalogator-tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(nowe)
        # sprawdzenie przed podmianą: obraz się otwiera, a GPS jest taki, jak trzeba
        with Image.open(tmp) as im:
            im.verify()
        with Image.open(tmp) as im:
            g = im.getexif().get_ifd(0x8825)
        if (lat is None) != (not g.get(2)):
            raise ValueError("zapis GPS nie powiódł się")
        os.replace(tmp, sciezka)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    os.utime(sciezka, (st.st_atime, st.st_mtime))  # data modyfikacji bez zmian
    _usun_nasz_xmp(sciezka)


def _xmp(lat: float | None, lon: float | None) -> bytes:
    if lat is None:
        gps = 'katalogator:Lokalizacja="brak"'
    else:
        def wsp(w, dod, uj):
            st = int(abs(w))
            return f"{st},{(abs(w) - st) * 60:.6f}{dod if w >= 0 else uj}"
        gps = (f'exif:GPSLatitude="{wsp(lat, "N", "S")}" exif:GPSLongitude="{wsp(lon, "E", "W")}" '
               f'katalogator:Lokalizacja="reczna"')
    return ('<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
            '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
            ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
            '  <rdf:Description rdf:about="" xmlns:exif="http://ns.adobe.com/exif/1.0/"\n'
            '    xmlns:katalogator="https://github.com/mbarczykmb-afk/chmura/ns/1.0/"\n'
            f'    {gps}/>\n'
            ' </rdf:RDF>\n'
            '</x:xmpmeta>\n<?xpacket end="w"?>\n').encode("utf-8")


def _nasz_xmp(sciezka: str) -> str:
    return sciezka + ".xmp"


def _usun_nasz_xmp(sciezka: str) -> None:
    x = _nasz_xmp(sciezka)
    try:
        with open(x, "rb") as f:
            if ZNACZNIK in f.read(100_000):
                os.remove(x)
    except OSError:
        pass


def _zapisz_xmp(sciezka: str, lat: float | None, lon: float | None) -> None:
    x = _nasz_xmp(sciezka)
    if os.path.exists(x):
        with open(x, "rb") as f:
            if ZNACZNIK not in f.read(100_000):
                raise ValueError(f"obok jest plik {os.path.basename(x)} innego programu — nie nadpisuję go")
    tmp = x + ".katalogator-tmp"
    with open(tmp, "wb") as f:
        f.write(_xmp(lat, lon))
    os.replace(tmp, x)


def zapisz_w_pliku(sciezka: str, lat: float | None, lon: float | None) -> None:
    if os.path.splitext(sciezka)[1].lower() in _JPEG:
        _zapisz_jpeg(sciezka, lat, lon)
    else:
        _zapisz_xmp(sciezka, lat, lon)


def ustaw(db: sqlite3.Connection, ids: list[int], lat: float | None, lon: float | None) -> dict:
    """Ustawia (lat, lon) albo usuwa lokalizację (None) wskazanym zdjęciom/filmom: w pliku i w bazie."""
    if lat is not None:
        lat, lon = float(lat), float(lon)
        if not (abs(lat) <= 90 and abs(lon) <= 180):
            return {"blad": "Nieprawidłowe współrzędne."}
        lat, lon = round(lat, 6), round(lon, 6)
    zmienione, bledy, poprzednie, sciezki = 0, [], {}, []
    for i in dict.fromkeys(int(x) for x in ids):
        r = db.execute("SELECT rowid, sciezka, wzgledna, rodzaj, rozmiar, mtime, lat, lon FROM pliki WHERE rowid=?",
                       (i,)).fetchone()
        if not r or r["rodzaj"] not in ("zdjecie", "film"):
            bledy.append("Plik nieaktualny — przeskanuj ponownie.")
            continue
        try:
            st = os.stat(r["sciezka"])
            if (st.st_size, st.st_mtime) != (r["rozmiar"], r["mtime"]):
                raise ValueError("plik zmienił się od skanu — przeskanuj ponownie")
            zapisz_w_pliku(r["sciezka"], lat, lon)
            st = os.stat(r["sciezka"])
        except (OSError, ValueError) as e:
            bledy.append(f"{r['wzgledna']}: {getattr(e, 'strerror', None) or e}")
            continue
        poprzednie[i] = [r["lat"], r["lon"]]
        db.execute("UPDATE pliki SET lat=?, lon=?, rozmiar=?, mtime=? WHERE rowid=?",
                   (lat, lon, st.st_size, st.st_mtime, i))
        try:  # zawartość JPEG-a się zmieniła — odcisk (duplikaty) policzymy od nowa
            db.execute("DELETE FROM odciski WHERE sciezka=?", (r["sciezka"],))
        except sqlite3.OperationalError:
            pass
        sciezki.append(r["sciezka"])
        zmienione += 1
    db.commit()
    indeks.usun(sciezki)
    return {"zmienione": zmienione, "bledy": bledy[:20], "poprzednie": poprzednie, "sciezki": sciezki,
            "lat": lat, "lon": lon}


def rozeslij(baza: str, sciezki: list[str], lat: float | None, lon: float | None) -> None:
    """Ta sama zmiana w innej bazie (inny projekt, Przeglądarka), gdzie te pliki też są."""
    try:
        db = sqlite3.connect(str(baza), timeout=10)
        try:
            for s in sciezki:
                try:
                    st = os.stat(s)
                except OSError:
                    continue
                db.execute("UPDATE pliki SET lat=?, lon=?, rozmiar=?, mtime=? WHERE sciezka=?",
                           (lat, lon, st.st_size, st.st_mtime, s))
            db.commit()
        finally:
            db.close()
    except sqlite3.Error:
        pass
