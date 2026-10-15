"""🛠 Naprawa odzyskanych filmów: diagnoza atomów MP4, ffmpeg, brak indeksu → potrzebny wzorzec."""
import os
import subprocess

import pytest

from katalogator import filmy, naprawa


def _atom(typ: bytes, dane: bytes) -> bytes:
    return (8 + len(dane)).to_bytes(4, "big") + typ + dane


def test_diagnoza_atomow(tmp_path):
    bez = tmp_path / "1.mp4"
    bez.write_bytes(_atom(b"ftyp", b"isom" + b"\0" * 8) + _atom(b"mdat", b"\1" * 1000))
    d = naprawa.diagnoza(str(bez))
    assert d["atomy"] == ["ftyp", "mdat"] and not d["moov"] and d["sposob"] == "wzorzec"
    ok = tmp_path / "2.mp4"
    ok.write_bytes(_atom(b"ftyp", b"isom" + b"\0" * 8) + _atom(b"moov", b"\0" * 50) + _atom(b"mdat", b"\1" * 100))
    assert naprawa.diagnoza(str(ok))["sposob"] == "ffmpeg"
    uciety = tmp_path / "3.mp4"
    uciety.write_bytes(_atom(b"ftyp", b"isom" + b"\0" * 8) + (5000).to_bytes(4, "big") + b"mdat" + b"\1" * 100)
    assert naprawa.atomy(str(uciety))[1] is True
    smiec = tmp_path / "4.mp4"
    smiec.write_bytes(b"to nie film" * 100)
    assert naprawa.diagnoza(str(smiec))["sposob"] is None
    (tmp_path / "x.avi").write_bytes(b"RIFF" + b"\0" * 100)
    assert naprawa.diagnoza(str(tmp_path / "x.avi"))["sposob"] == "ffmpeg"


@pytest.mark.skipif(not filmy.ffmpeg(), reason="brak ffmpeg")
def test_naprawa_ffmpeg_i_brak_indeksu(tmp_path):
    film = tmp_path / "film.mp4"
    subprocess.run([filmy.ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10",
                    "-t", "2", "-pix_fmt", "yuv420p", str(film)], check=True)
    w = naprawa.napraw(str(film), tmp_path)
    assert w["ok"] and w["sciezka"].endswith("film_naprawiony.mp4") and os.path.exists(w["sciezka"])
    # odzyskane „po sygnaturze”: nagłówek i dane są, indeksu (moov) brak
    a, _ = naprawa.atomy(str(film))
    dane = film.read_bytes()
    bez = tmp_path / "7.mp4"
    bez.write_bytes(b"".join(dane[p:p + n] for t, p, n in a if t != "moov"))
    w = naprawa.napraw(str(bez), tmp_path)
    assert w.get("potrzebny_wzorzec") and not w.get("ok")
    assert naprawa.filmy_w(str(tmp_path))[0]["nazwa"] == "7.mp4"
