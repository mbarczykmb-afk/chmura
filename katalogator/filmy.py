"""Filmy w każdym formacie — także bardzo stare (2000–2012): AVI z DivX/Xvid/MS-MPEG4/MJPEG, MPG/VOB (MPEG-1/2),
3GP/H.263 z telefonów, WMV, FLV, MOD/TOD/MTS z kamer, DV, Indeo, Cinepak…

Przeglądarka (okno programu, telefon) sama odtwarza tylko MP4/H.264 i WebM. Resztę ffmpeg przerabia w locie na
MP4 (H.264 + AAC, „fragmentowany” — odtwarzanie rusza od razu, bez czekania na cały plik); przeplot ze starych kamer
jest usuwany. Miniatura = klatka z ~1. sekundy. Oryginalny plik nie jest zmieniany.

ffmpeg: obok programu (instalator: <program>/ffmpeg/ffmpeg.exe), z pakietu imageio-ffmpeg albo z PATH.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .logi import LOG

# te zwykle odtworzy sama przeglądarka (H.264 / VP8 / VP9 / AV1); gdy nie (np. HEVC z iPhone'a) — przerabiamy
NATYWNE = {".mp4", ".m4v", ".mov", ".webm"}
_BEZ_OKNA = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW — bez migającej konsoli
_sciezka: list = []


def ffmpeg() -> str | None:
    """Ścieżka do ffmpeg albo None (wtedy filmy tylko w formatach, które zna przeglądarka)."""
    if _sciezka:
        return _sciezka[0]
    kandydaci = [os.environ.get("KATALOGATOR_FFMPEG")]
    exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    for baza in (getattr(sys, "_MEIPASS", None), os.path.dirname(sys.executable), Path(__file__).parent.parent):
        if baza:
            kandydaci.append(os.path.join(str(baza), "ffmpeg", exe))
    try:
        import imageio_ffmpeg
        kandydaci.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    kandydaci.append(shutil.which("ffmpeg"))
    znaleziony = next((k for k in kandydaci if k and os.path.isfile(k)), None)
    _sciezka.append(znaleziony)
    LOG.info("ffmpeg: %s", znaleziony or "brak — stare formaty filmów bez podglądu")
    return znaleziony


def klatka(sciezka: str, szer: int = 480, sekunda: float = 1.0) -> bytes | None:
    """JPEG z klatki filmu (ok. 1. sekunda; krótszy film — pierwsza klatka)."""
    f = ffmpeg()
    if not f or not os.path.isfile(sciezka):
        return None
    for ss in (sekunda, 0):
        try:
            w = subprocess.run(
                [f, "-hide_banner", "-loglevel", "error", "-ss", str(ss), "-i", sciezka, "-frames:v", "1",
                 "-vf", f"yadif=deint=interlaced,scale='min({szer},iw)':-2", "-q:v", "4",
                 "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45,
                creationflags=_BEZ_OKNA)
        except (OSError, subprocess.TimeoutExpired) as e:
            LOG.info("Klatka filmu %s: %s", sciezka, e)
            return None
        if w.stdout.startswith(b"\xff\xd8"):
            return w.stdout
    LOG.info("Klatka filmu %s: %s", sciezka, w.stderr.decode(errors="replace")[-300:])
    return None


def polecenie_mp4(sciezka: str, od: float = 0, webm: bool = False) -> list[str] | None:
    """MP4 (H.264 + AAC) — najszerzej obsługiwany; WebM (VP8 + Opus) — zapas, gdy w systemie brak H.264
    (np. Windows „N” bez pakietu multimediów)."""
    f = ffmpeg()
    if not f:
        return None
    wejscie = [f, "-hide_banner", "-loglevel", "error", *(["-ss", f"{od:.2f}"] if od > 0 else []), "-i", sciezka,
               "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn",
               "-vf", "yadif=deint=interlaced,scale='min(1280,iw)':-2,format=yuv420p"]
    if webm:
        return wejscie + ["-c:v", "libvpx", "-deadline", "realtime", "-cpu-used", "8", "-b:v", "2M", "-g", "48",
                          "-c:a", "libopus", "-b:a", "128k", "-ac", "2", "-f", "webm", "pipe:1"]
    return wejscie + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-g", "48",
                      "-c:a", "aac", "-b:a", "128k", "-ac", "2",
                      "-movflags", "frag_keyframe+empty_moov+default_base_moof", "-f", "mp4", "pipe:1"]


def wyslij_mp4(handler, sciezka: str | None, od: float = 0, webm: bool = False) -> None:
    """Strumień MP4 przerabiany w locie — do <video>. Koniec połączenia = koniec filmu (bez długości z góry)."""
    from http import HTTPStatus
    pol = polecenie_mp4(sciezka, od, webm) if sciezka and os.path.isfile(sciezka) else None
    if not pol:
        handler.send_response(HTTPStatus.NOT_FOUND)
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        tresc = ("Brak ffmpeg — ten format filmu da się otworzyć tylko w programie Windows." if not ffmpeg()
                 else "Nie ma takiego filmu.").encode()
        handler.send_header("Content-Length", str(len(tresc)))
        handler.end_headers()
        handler.wfile.write(tresc)
        return
    proc = subprocess.Popen(pol, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            creationflags=_BEZ_OKNA)
    try:
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "video/webm" if webm else "video/mp4")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.close_connection = True
        while True:
            kawalek = proc.stdout.read(64 * 1024)
            if not kawalek:
                break
            handler.wfile.write(kawalek)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
        pass  # okno zamknięte / przewinięte — przerywamy przerabianie
    finally:
        proc.kill()
        proc.wait(timeout=10)
