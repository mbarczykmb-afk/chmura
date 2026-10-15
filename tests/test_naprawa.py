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


def _mp4(sciezka, marka=b"isom", moov=True, rozmiar=2000):
    dane = _atom(b"ftyp", marka + b"\0\0\0\0" + marka + b"avc1") + (_atom(b"moov", b"\0" * 40) if moov else b"")
    sciezka.write_bytes(dane + _atom(b"mdat", b"\1" * rozmiar))


def test_tekst_i_ftyp(tmp_path):
    (tmp_path / "a.d.mts").write_text("export declare function f(): void;\n" * 30)
    assert naprawa.to_tekst(str(tmp_path / "a.d.mts")) and naprawa.diagnoza(str(tmp_path / "a.d.mts"))["tekst"]
    _mp4(tmp_path / "z.mp4", b"mp42")
    assert naprawa.ftyp(str(tmp_path / "z.mp4")) == ("mp42", ["mp42", "avc1"])


def test_wzorzec_dobierany_sam(tmp_path, monkeypatch):
    zepsuty = tmp_path / "odzysk" / "1.mp4"
    zepsuty.parent.mkdir()
    _mp4(zepsuty, b"mp42", moov=False, rozmiar=5000)
    for n, m in (("inny.mp4", b"qt  "), ("podobny.mp4", b"mp42"), ("bez_indeksu.mp4", b"mp42")):
        _mp4(tmp_path / n, m, moov=n != "bez_indeksu.mp4", rozmiar=6000)
    filmy_ = [str(tmp_path / n) for n in ("inny.mp4", "podobny.mp4", "bez_indeksu.mp4")] + [str(zepsuty)]
    k = naprawa.kandydaci(str(zepsuty), filmy_, pomin=str(zepsuty.parent))
    assert k[0].endswith("podobny.mp4") and not any(x.endswith("bez_indeksu.mp4") for x in k)
    proby = []

    def udawany_untrunc(sc, wz, katalog):
        proby.append(os.path.basename(wz))
        return {"ok": True, "sciezka": sc + "_naprawiony.mp4"} if wz.endswith("podobny.mp4") else {"blad": "nie"}
    monkeypatch.setattr(naprawa, "napraw_ffmpeg", lambda sc: {"blad": "brak moov"})
    monkeypatch.setattr(naprawa, "napraw_wzorcem", udawany_untrunc)
    pamiec = {}
    w = naprawa.napraw_auto(str(zepsuty), tmp_path, filmy_, pamiec, str(zepsuty.parent))
    assert w["ok"] and w["wzorzec"].endswith("podobny.mp4") and pamiec["mp42"][0].endswith("podobny.mp4")
    assert proby == ["podobny.mp4"]
