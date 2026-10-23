"""🌍 Most do domu: zdalna Przeglądarka bez VPN-u na komputerze w pracy.

Katalogator w domu wystawia serwer Przeglądarki (ten sam, co dla telefonu) pod stałym adresem HTTPS
`https://<komputer>.<tailnet>.ts.net/` przez Tailscale Funnel. Tailscale jest potrzebny tylko na komputerze w domu —
w pracy wystarczy Katalogator albo zwykła przeglądarka i link z kluczem. Przez most nie działa PIN telefonu: wejście
tylko po długim kluczu, i tylko do oglądania (bez pilota, usuwania i pełnego programu).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import sys

_BEZ_OKNA = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
_ALFABET = "abcdefghjkmnpqrstuvwxyz23456789"  # bez 0/o, 1/l/i — łatwo przepisać z kartki


def nowy_klucz() -> str:
    """Np. „k7pq2-9hm4x-tz3ab-w8ncd” — ok. 98 bitów losowości."""
    return "-".join("".join(secrets.choice(_ALFABET) for _ in range(5)) for _ in range(4))


def normalizuj_klucz(k: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (k or "").lower())


def tailscale() -> str | None:
    """Ścieżka do programu `tailscale` (Windows: w Program Files, inne: w PATH)."""
    kandydaci = [os.environ.get("KATALOGATOR_TAILSCALE"), shutil.which("tailscale")]
    if sys.platform == "win32":
        for z in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            if os.environ.get(z):
                kandydaci.append(os.path.join(os.environ[z], "Tailscale", "tailscale.exe"))
    return next((k for k in kandydaci if k and os.path.isfile(k)), None)


def _uruchom(argumenty: list[str], czas: int = 25) -> tuple[int, str]:
    exe = tailscale()
    if not exe:
        return 127, ""
    try:
        w = subprocess.run([exe, *argumenty], capture_output=True, text=True, timeout=czas,
                           stdin=subprocess.DEVNULL, creationflags=_BEZ_OKNA)
        return w.returncode, (w.stdout or "") + (w.stderr or "")
    except subprocess.TimeoutExpired as e:  # czeka na włączenie Funnel w panelu — oddajemy to, co już wypisał
        tekst = e.stdout or b""
        tekst = (tekst.decode("utf-8", "replace") if isinstance(tekst, bytes) else tekst)
        err = e.stderr or b""
        tekst += err.decode("utf-8", "replace") if isinstance(err, bytes) else err
        return -1, tekst
    except OSError as e:
        return 126, str(e)


def stan() -> dict:
    """Czy Tailscale jest zainstalowany i zalogowany; nazwa komputera w tailnecie (do adresu mostu)."""
    if not tailscale():
        return {"tailscale": False}
    kod, tekst = _uruchom(["status", "--json"], 15)
    try:
        j = json.loads(tekst[tekst.index("{"):]) if "{" in tekst else {}
    except ValueError:
        j = {}
    ja = j.get("Self") or {}
    dns = (ja.get("DNSName") or "").rstrip(".")
    return {"tailscale": True, "zalogowany": j.get("BackendState") == "Running", "dns": dns,
            "adres": f"https://{dns}/" if dns else ""}


def _link(tekst: str) -> str:
    m = re.search(r"https://login\.tailscale\.com/\S+", tekst or "")
    return m.group(0).rstrip(".,)") if m else ""


def sprawdz() -> dict:
    """Stan Tailscale albo {"blad": …} — zanim cokolwiek włączymy."""
    s = stan()
    if not s.get("tailscale"):
        return {"blad": "Na tym komputerze nie ma Tailscale. Zainstaluj go (tailscale.com/download), zaloguj się i spróbuj "
                        "ponownie — potrzebny jest tylko tutaj, w domu.", "link": "https://tailscale.com/download"}
    if not s.get("zalogowany"):
        return {"blad": "Tailscale nie jest połączony — kliknij jego ikonę obok zegara i zaloguj się."}
    return s


def wlacz(port: int) -> dict:
    """Funnel: https://<komputer>.ts.net/ → http://127.0.0.1:<port> (zostaje włączony także po restarcie)."""
    s = sprawdz()
    if "blad" in s:
        return s
    kod, tekst = _uruchom(["funnel", "--bg", str(int(port))])
    if kod != 0:
        link = _link(tekst)
        if link:
            return {"blad": "Tailscale prosi o jednorazową zgodę na Funnel (udostępnianie przez internet). Otwórz link, "
                            "zatwierdź i kliknij „Włącz most” jeszcze raz.", "link": link}
        return {"blad": "Nie udało się włączyć mostu: " + (tekst.strip().splitlines() or ["brak odpowiedzi"])[-1][:300]}
    return {"ok": True, "adres": s["adres"]}


def wylacz() -> dict:
    for argumenty in (["funnel", "--https=443", "off"], ["funnel", "reset"]):
        kod, _ = _uruchom(argumenty, 15)
        if kod == 0:
            return {"ok": True}
    return {"blad": "Nie udało się wyłączyć mostu w Tailscale — wyłącz go poleceniem: tailscale funnel reset"}
