import struct
from datetime import datetime, timezone

import pytest
from PIL import Image

from katalogator import metadane


def _tiff_z_exif(sciezka, data="2021:06:05 14:30:00", gps=(50.2811, 19.5625), bo="<"):
    """Minimalny TIFF jak w plikach RAW: IFD0 (Make, Model, wskaźniki Exif/GPS), Exif IFD, GPS IFD."""
    dane = bytearray()
    wpisy_cache = []

    def ascii_(t):
        return t.encode() + b"\0"

    def rac(*w):
        out = b""
        for x in w:
            out += struct.pack(bo + "II", int(round(x * 1000)), 1000)
        return out

    # układ: nagłówek(8) | IFD0 | Exif IFD | GPS IFD | dane
    def ifd(wpisy, poz_ifd, poz_danych):
        """wpisy: [(tag, typ, licz, bajty)] -> (bajty IFD, bajty danych)."""
        blok, extra = struct.pack(bo + "H", len(wpisy)), b""
        for tag, typ, licz, b in wpisy:
            if len(b) <= 4:
                blok += struct.pack(bo + "HHI", tag, typ, licz) + b.ljust(4, b"\0")
            else:
                blok += struct.pack(bo + "HHII", tag, typ, licz, poz_danych + len(extra))
                extra += b + (b"\0" if len(b) % 2 else b"")
        return blok + struct.pack(bo + "I", 0), extra

    make, model = ascii_("NIKON CORPORATION"), ascii_("NIKON D750")
    poz0 = 8
    n0 = 4 if gps else 3
    rozm0 = 2 + 12 * n0 + 4
    poz_ex = poz0 + rozm0 + 64
    rozm_ex = 2 + 12 + 4
    poz_gps = poz_ex + rozm_ex + 32
    rozm_gps = 2 + 12 * 4 + 4
    poz_dane = poz_gps + rozm_gps + 16
    d = ascii_(data)
    ex_blok, ex_extra = ifd([(36867, 2, len(d), d)], poz_ex, poz_dane)
    poz_dane2 = poz_dane + len(ex_extra)
    w0 = [(0x010F, 2, len(make), make), (0x0110, 2, len(model), model),
          (0x8769, 4, 1, struct.pack(bo + "I", poz_ex))]
    if gps:
        w0.append((0x8825, 4, 1, struct.pack(bo + "I", poz_gps)))
    ifd0_blok, ifd0_extra = ifd(w0, poz0, poz_dane2)
    poz_dane3 = poz_dane2 + len(ifd0_extra)
    gps_blok, gps_extra = b"", b""
    if gps:
        def dms(x):
            st = int(x); mi = int((x - st) * 60); return st, mi, ((x - st) * 60 - mi) * 60
        gps_blok, gps_extra = ifd([(1, 2, 2, b"N\0"), (2, 5, 3, rac(*dms(gps[0]))), (3, 2, 2, b"E\0"),
                                   (4, 5, 3, rac(*dms(gps[1])))], poz_gps, poz_dane3)
    plik = bytearray(poz_dane3 + len(gps_extra) + 16)
    plik[0:8] = (b"II" if bo == "<" else b"MM") + struct.pack(bo + "HI", 42, poz0)
    plik[poz0:poz0 + len(ifd0_blok)] = ifd0_blok
    plik[poz_ex:poz_ex + len(ex_blok)] = ex_blok
    if gps:
        plik[poz_gps:poz_gps + len(gps_blok)] = gps_blok
    plik[poz_dane:poz_dane + len(ex_extra)] = ex_extra
    plik[poz_dane2:poz_dane2 + len(ifd0_extra)] = ifd0_extra
    plik[poz_dane3:poz_dane3 + len(gps_extra)] = gps_extra
    with open(sciezka, "wb") as f:
        f.write(bytes(plik))


@pytest.mark.parametrize("ext,bo", [(".dng", "<"), (".nef", ">"), (".cr2", "<"), (".arw", "<")])
def test_raw_tiff(tmp_path, ext, bo):
    p = tmp_path / ("DSC_0001" + ext)
    _tiff_z_exif(p, bo=bo)
    m = metadane.odczytaj(str(p), "zdjecie", 0)
    assert (m.data, m.zrodlo_daty) == (datetime(2021, 6, 5, 14, 30), "exif"), m.blad
    assert m.aparat == "NIKON D750"
    assert m.lat == pytest.approx(50.2811, abs=1e-3) and m.lon == pytest.approx(19.5625, abs=1e-3)


def test_raw_z_nietypowym_naglowkiem(tmp_path):
    p = tmp_path / "P1010001.ORF"
    _tiff_z_exif(p, gps=None)
    b = bytearray(p.read_bytes())
    b[2:4] = b"RO"  # Olympus zamiast 42
    p.write_bytes(bytes(b))
    m = metadane.odczytaj(str(p), "zdjecie", 0)
    assert m.data == datetime(2021, 6, 5, 14, 30)


def test_uszkodzony_raw_bierze_date_z_pliku(tmp_path):
    p = tmp_path / "zly.cr2"
    p.write_bytes(b"II*\0\xff\xff\xff\x7f" + b"\0" * 20)
    m = metadane.odczytaj(str(p), "zdjecie", 1_600_000_000)
    assert m.zrodlo_daty == "plik"


def _riff(chunki):
    dane = b"".join(k + struct.pack("<I", len(v)) + v + (b"\0" if len(v) % 2 else b"") for k, v in chunki)
    return b"RIFF" + struct.pack("<I", 4 + len(dane)) + b"AVI " + dane


@pytest.mark.parametrize("tekst,oczek", [
    (b"THU OCT 26 16:46:04 2006\n\0", datetime(2006, 10, 26, 16, 46, 4)),
    (b"2009:07:18 10:20:30\0", datetime(2009, 7, 18, 10, 20, 30)),
])
def test_avi(tmp_path, tekst, oczek):
    p = tmp_path / "MOV001.AVI"
    p.write_bytes(_riff([(b"LIST", b"hdrl" + b"IDIT" + struct.pack("<I", len(tekst)) + tekst), (b"movi", b"\0" * 64)]))
    m = metadane.odczytaj(str(p), "film", 0)
    assert (m.data, m.zrodlo_daty) == (oczek, "film")


def _ebml(eid: bytes, dane: bytes) -> bytes:
    n = len(dane)
    return eid + bytes([0x01, 0, 0, 0, 0, 0, (n >> 8) & 0xFF, n & 0xFF]) if False else eid + (0x10000000 | n).to_bytes(4, "big") + dane


def test_mkv(tmp_path):
    kiedy = datetime(2018, 8, 15, 12, 0, tzinfo=timezone.utc)
    ns = int((kiedy - datetime(2001, 1, 1, tzinfo=timezone.utc)).total_seconds() * 1e9)
    info = _ebml(b"\x15\x49\xa9\x66", _ebml(b"\x2a\xd7\xb1", b"\x0f\x42\x40"[:3]) + b"\x44\x61\x88" + struct.pack(">q", ns))
    seg = b"\x18\x53\x80\x67" + b"\x01\xff\xff\xff\xff\xff\xff\xff" + info + _ebml(b"\x1f\x43\xb6\x75", b"\0" * 32)
    p = tmp_path / "film.mkv"
    p.write_bytes(_ebml(b"\x1a\x45\xdf\xa3", b"\x42\x82\x88matroska") + seg)
    m = metadane.odczytaj(str(p), "film", 0)
    assert m.zrodlo_daty == "film"
    assert m.data == kiedy.astimezone().replace(tzinfo=None)


def test_heic(tmp_path):
    pillow_heif = pytest.importorskip("pillow_heif")
    pillow_heif.register_heif_opener()
    p = tmp_path / "IMG_0001.HEIC"
    im = Image.new("RGB", (64, 48), "red")
    ex = im.getexif()
    ex[0x0110] = "iPhone 13"
    ex.get_ifd(0x8769)[36867] = "2022:05:01 10:00:00"
    im.save(p, exif=ex)
    m = metadane.odczytaj(str(p), "zdjecie", 0)
    assert (m.data, m.zrodlo_daty, m.aparat) == (datetime(2022, 5, 1, 10), "exif", "iPhone 13")
    from katalogator import analiza
    mini, rozm = analiza.miniatura(str(p))
    assert rozm == (64, 48)
