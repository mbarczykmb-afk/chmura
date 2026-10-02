"""Filmy w starych formatach (AVI/DivX, MPG z przeplotem, 3GP, WMV): klatka do miniatury i MP4/WebM w locie."""

import io
import subprocess

import pytest

from katalogator import aplikacja, filmy

pytestmark = pytest.mark.skipif(not filmy.ffmpeg(), reason="brak ffmpeg")


def _film(sciezka, *opcje):
    subprocess.run([filmy.ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=320x240:rate=25:duration=2", *opcje, str(sciezka)], check=True)


@pytest.mark.parametrize("nazwa,opcje", [
    ("divx_2009.avi", ["-c:v", "msmpeg4v2"]),
    ("kamera.mpg", ["-c:v", "mpeg2video", "-flags", "+ilme+ildct"]),
    ("telefon.3gp", ["-s", "176x144", "-c:v", "h263"]),
    ("stary.wmv", ["-c:v", "wmv2"]),
])
def test_stare_formaty(tmp_path, nazwa, opcje):
    p = tmp_path / nazwa
    _film(p, *opcje)
    k = filmy.klatka(str(p), 200)
    assert k and k.startswith(b"\xff\xd8")
    from PIL import Image
    assert Image.open(io.BytesIO(k)).size[0] <= 200  # nie powiększamy małych (3GP 176 px)
    for webm in (False, True):
        w = subprocess.run(filmy.polecenie_mp4(str(p), webm=webm), capture_output=True, timeout=60)
        assert w.returncode == 0 and len(w.stdout) > 1000
        assert w.stdout[4:8] == b"ftyp" if not webm else w.stdout[:4] == b"\x1a\x45\xdf\xa3"


def test_film_w_programie(tmp_path):
    import time
    zr = tmp_path / "filmy"
    zr.mkdir()
    _film(zr / "stary.avi", "-c:v", "mpeg4")
    stan = aplikacja.Stan(tmp_path / "dane")
    stan.zapisz_ustawienia({"zrodla": [{"sciezka": str(zr), "tryb": "kopiuj"}], "cel": ""})
    stan.rozpocznij_skan()
    while stan.zajety():
        time.sleep(0.05)
    fid = stan.z_db(lambda db: db.execute("SELECT rowid FROM pliki WHERE rodzaj='film'").fetchone()[0])
    j = stan.miniatura_filmu(fid)
    assert j.startswith(b"\xff\xd8") and stan.miniatura_filmu(fid) == j  # druga — z pamięci na dysku
    assert stan.galeria("wszystko").miniatura(fid).startswith(b"\xff\xd8")  # galeria i telefon — klatka z ffmpeg
