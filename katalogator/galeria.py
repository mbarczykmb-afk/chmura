"""Przeglądarka biblioteki: oś czasu (lata → miesiące) i mapa miejsc (OpenStreetMap).

Działa w oknie programu (dane projektu) i jako osobny serwer tylko do odczytu dla telefonu —
z komputera (sieć domowa / Tailscale, z PIN-em) albo 24/7 z Raspberry Pi:
    python -m katalogator galeria --folder /mnt/mycloud/Biblioteka --pin 1234
"""

from __future__ import annotations

import io
import json
import os
import re
import secrets
import socket
import threading
import time
from collections import OrderedDict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import analiza, miejsca, skaner

UI = Path(__file__).parent / "ui"
_TYPY = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".png": "image/png",
         ".ico": "image/x-icon", ".html": "text/html; charset=utf-8", ".svg": "image/svg+xml"}


def plik_ui(sciezka_url: str) -> tuple[bytes, str] | None:
    """Plik interfejsu spod /ui/… (także podfoldery, np. /ui/mapa/leaflet.js) — nigdy spoza katalogu ui."""
    wzgl = sciezka_url[len("/ui/"):] if sciezka_url.startswith("/ui/") else ""
    p = (UI / wzgl).resolve()
    if not wzgl or UI.resolve() not in p.parents or p.suffix not in _TYPY or not p.is_file():
        return None
    return p.read_bytes(), _TYPY[p.suffix]


class Galeria:
    """Dane dla osi czasu i mapy z bazy skanu. korzenie() -> lista folderów (None = wszystko w bazie)."""

    def __init__(self, baza, korzenie=None, pamiec_min: Path | None = None):
        self.baza = baza
        self.korzenie = korzenie or (lambda: None)
        self.pamiec_min = pamiec_min  # katalog na miniatury (serwer 24/7) — w oknie tylko pamięć RAM
        self._min: OrderedDict = OrderedDict()
        self._blokada = threading.Lock()

    def _db(self):
        return skaner.otworz_baze(self.baza)

    def _warunek(self) -> tuple[str, list]:
        k = self.korzenie()
        if not k:
            return "", []
        czesci, arg = [], []
        for r in k:
            r = os.path.abspath(r)
            pref = r.rstrip("\\/") + os.sep
            czesci.append("(korzen = ? OR substr(sciezka, 1, ?) = ?)")
            arg += [r, len(pref), pref]
        return " AND (" + " OR ".join(czesci) + ")", arg

    def lata(self) -> dict:
        w, arg = self._warunek()
        db = self._db()
        try:
            lata: dict[str, dict] = {}
            for r in db.execute(
                    f"""SELECT substr(data, 1, 4) rok, CAST(substr(data, 6, 2) AS INTEGER) mies, COUNT(*) n,
                               SUM(lat IS NOT NULL) gps FROM pliki
                        WHERE rodzaj IN ('zdjecie', 'film') AND data IS NOT NULL {w}
                        GROUP BY rok, mies ORDER BY rok DESC, mies DESC""", arg):
                rok = lata.setdefault(r["rok"], {"rok": r["rok"], "n": 0, "gps": 0, "miesiace": []})
                rok["n"] += r["n"]
                rok["gps"] += r["gps"] or 0
                rok["miesiace"].append({"m": r["mies"], "n": r["n"]})
            bez = db.execute(f"SELECT COUNT(*) FROM pliki WHERE rodzaj IN ('zdjecie','film') AND data IS NULL {w}",
                             arg).fetchone()[0]
        finally:
            db.close()
        l = list(lata.values())
        return {"lata": l, "razem": sum(x["n"] for x in l) + bez, "z_gps": sum(x["gps"] for x in l),
                "bez_daty": bez}

    def pliki(self, rok: str, miesiac: int | None, od: int = 0, ile: int = 200) -> dict:
        w, arg = self._warunek()
        filtr = "substr(data, 1, 4) = ?" + (" AND CAST(substr(data, 6, 2) AS INTEGER) = ?" if miesiac else "")
        a = [str(rok)] + ([int(miesiac)] if miesiac else [])
        db = self._db()
        try:
            razem = db.execute(f"SELECT COUNT(*) FROM pliki WHERE rodzaj IN ('zdjecie','film') AND {filtr} {w}",
                               a + arg).fetchone()[0]
            wiersze = [dict(r) for r in db.execute(
                f"""SELECT rowid id, wzgledna, rodzaj, data, lat, lon, rozmiar FROM pliki
                    WHERE rodzaj IN ('zdjecie','film') AND {filtr} {w} ORDER BY data, wzgledna LIMIT ? OFFSET ?""",
                a + arg + [int(ile), int(od)])]
        finally:
            db.close()
        for r in wiersze:
            r["nazwa"] = re.split(r"[\\/]", r.pop("wzgledna"))[-1]
        return {"razem": razem, "pliki": wiersze}

    def mapa(self) -> dict:
        """Wszystkie zdjęcia i filmy z GPS — zwięźle: [id, lat, lon, 1 = film]."""
        w, arg = self._warunek()
        db = self._db()
        try:
            punkty = [[r[0], round(r[1], 5), round(r[2], 5), 1 if r[3] == "film" else 0] for r in db.execute(
                f"""SELECT rowid, lat, lon, rodzaj FROM pliki
                    WHERE rodzaj IN ('zdjecie','film') AND lat IS NOT NULL AND lon IS NOT NULL {w}""", arg)]
        finally:
            db.close()
        return {"punkty": punkty}

    def _wiersz(self, id_: int):
        w, arg = self._warunek()
        db = self._db()
        try:
            return db.execute(f"SELECT rowid id, * FROM pliki WHERE rowid = ? {w}", [int(id_)] + arg).fetchone()
        finally:
            db.close()

    def plik(self, id_: int) -> dict | None:
        r = self._wiersz(id_)
        if not r:
            return None
        miejsce = None
        if r["lat"] is not None:
            try:
                e = miejsca.etykieta(r["lat"], r["lon"])
                miejsce = e if not e.startswith("@") else miejsca.fraza(e)
            except Exception:
                miejsce = None
        return {"id": r["id"], "nazwa": re.split(r"[\\/]", r["wzgledna"])[-1], "folder": os.path.dirname(r["wzgledna"]),
                "data": r["data"], "rodzaj": r["rodzaj"], "aparat": r["aparat"], "lat": r["lat"], "lon": r["lon"],
                "miejsce": miejsce, "rozmiar": r["rozmiar"]}

    def sciezka(self, id_: int, rodzaj: str | None = None) -> str | None:
        r = self._wiersz(id_)
        if not r or (rodzaj and r["rodzaj"] != rodzaj):
            return None
        return r["sciezka"]

    def miniatura(self, id_: int, srednia: bool = False) -> bytes | None:
        klucz = (int(id_), srednia)
        with self._blokada:
            if klucz in self._min:
                self._min.move_to_end(klucz)
                return self._min[klucz]
        plik_cache = self.pamiec_min / f"{id_}{'s' if srednia else ''}.jpg" if self.pamiec_min else None
        sc = self.sciezka(id_, "zdjecie")
        if not sc:
            return None
        dane = None
        if plik_cache and plik_cache.exists() and plik_cache.stat().st_mtime >= os.path.getmtime(sc):
            dane = plik_cache.read_bytes()
        if dane is None:
            try:
                if srednia:
                    im, _ = analiza.miniatura(sc, min_bok=200)
                    im.thumbnail((600, 600))
                else:
                    im, _ = analiza.miniatura(sc, min_bok=150)
                    im.thumbnail((260, 260))
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=82)
                dane = buf.getvalue()
            except Exception:
                return None
            if plik_cache:
                try:
                    plik_cache.parent.mkdir(parents=True, exist_ok=True)
                    plik_cache.write_bytes(dane)
                except OSError:
                    pass
        with self._blokada:
            self._min[klucz] = dane
            while len(self._min) > 800:
                self._min.popitem(last=False)
        return dane

    def podglad(self, id_: int) -> bytes | None:
        sc = self.sciezka(id_, "zdjecie")
        if not sc:
            return None
        try:
            im = analiza._obraz_do_tekstu(sc, bok=1800)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=86)
            return buf.getvalue()
        except Exception:
            return None


def wyslij_strumien(h: BaseHTTPRequestHandler, sciezka: str | None) -> None:
    """Film z obsługą zakresów (Range) — przeglądarka czyta tylko potrzebny fragment."""
    if not sciezka or not os.path.isfile(sciezka):
        h.send_response(HTTPStatus.NOT_FOUND)
        h.send_header("Content-Length", "0")
        h.end_headers()
        return
    rozm = os.path.getsize(sciezka)
    typ = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/mp4", ".3gp": "video/3gpp",
           ".webm": "video/webm", ".mkv": "video/webm"}.get(Path(sciezka).suffix.lower(), "application/octet-stream")
    start, koniec = 0, rozm - 1
    m = re.match(r"bytes=(\d*)-(\d*)", h.headers.get("Range", ""))
    if m and (m.group(1) or m.group(2)):
        if m.group(1):
            start = int(m.group(1))
            koniec = min(int(m.group(2)) if m.group(2) else rozm - 1, rozm - 1)
        else:
            start = max(0, rozm - int(m.group(2)))
        if start > koniec:
            h.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            h.send_header("Content-Range", f"bytes */{rozm}")
            h.end_headers()
            return
        h.send_response(HTTPStatus.PARTIAL_CONTENT)
        h.send_header("Content-Range", f"bytes {start}-{koniec}/{rozm}")
    else:
        h.send_response(HTTPStatus.OK)
    h.send_header("Content-Type", typ)
    h.send_header("Accept-Ranges", "bytes")
    h.send_header("Content-Length", str(koniec - start + 1))
    h.end_headers()
    try:
        with open(sciezka, "rb") as f:
            f.seek(start)
            zostalo = koniec - start + 1
            while zostalo > 0:
                k = f.read(min(1 << 20, zostalo))
                if not k:
                    break
                h.wfile.write(k)
                zostalo -= len(k)
    except (ConnectionError, OSError):
        pass  # przeglądarka przerwała pobieranie (np. przewinięcie) — to normalne


def obsluz_api(g: Galeria, sciezka: str, q: dict):
    """/api/g/… -> (treść, typ) albo („film”, ścieżka) albo None, gdy to nie ścieżka galerii."""
    def i(k, d=0):
        try:
            return int(q.get(k, [d])[0])
        except (TypeError, ValueError):
            return d
    if sciezka == "/api/g/lata":
        return g.lata(), None
    if sciezka == "/api/g/pliki":
        return g.pliki(q.get("rok", [""])[0], i("miesiac") or None, i("od"), min(i("ile", 200), 500)), None
    if sciezka == "/api/g/mapa":
        return g.mapa(), None
    if sciezka == "/api/g/plik":
        return g.plik(i("id")) or {"blad": "nie ma takiego pliku"}, None
    if sciezka == "/api/g/miniatura":
        return g.miniatura(i("id"), bool(q.get("srednia"))), "image/jpeg"
    if sciezka == "/api/g/podglad":
        return g.podglad(i("id")), "image/jpeg"
    if sciezka == "/api/g/film":
        return "film", g.sciezka(i("id"), "film")
    return None


# --- serwer dla telefonu (tylko odczyt, PIN) ------------------------------------------------------

def adresy_ip() -> list[str]:
    """Adresy tego komputera w sieci domowej i w Tailscale (100.x) — do wpisania w telefonie."""
    wynik = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in wynik:
                wynik.append(ip)
    except OSError:
        pass
    try:  # adres „wychodzący” (bez wysyłania czegokolwiek)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.0.1", 9))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127.") and ip not in wynik:
            wynik.insert(0, ip)
    except OSError:
        pass
    return sorted(wynik, key=lambda a: (not a.startswith(("192.168.", "10.", "172.")), not a.startswith("100.")))


class SerwerGalerii:
    """HTTP tylko do odczytu na wszystkich interfejsach; dostęp po PIN-ie (token w przeglądarce telefonu)."""

    def __init__(self, galeria: Galeria, port: int = 8765, pin: str | None = None, host: str = "0.0.0.0"):
        self.galeria = galeria
        self.pin = pin or f"{secrets.randbelow(10**6):06d}"
        self.tokeny: set[str] = set()
        self.nieudane: dict[str, list[float]] = {}
        self.serwer = ThreadingHTTPServer((host, port), self._handler())
        self.serwer.daemon_threads = True
        self.port = self.serwer.server_address[1]
        self.watek: threading.Thread | None = None

    def start(self) -> "SerwerGalerii":
        self.watek = threading.Thread(target=self.serwer.serve_forever, daemon=True)
        self.watek.start()
        return self

    def stop(self) -> None:
        self.serwer.shutdown()
        self.serwer.server_close()

    def adresy(self) -> list[str]:
        return [f"http://{ip}:{self.port}/" for ip in adresy_ip()]

    def _handler(self):
        s = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _wyslij(self, tresc, typ="application/json; charset=utf-8", kod=HTTPStatus.OK):
                if tresc is None:
                    tresc, typ, kod = b"", "text/plain", HTTPStatus.NOT_FOUND
                dane = (json.dumps(tresc, ensure_ascii=False).encode() if not isinstance(tresc, (bytes, str))
                        else tresc.encode() if isinstance(tresc, str) else tresc)
                self.send_response(kod)
                self.send_header("Content-Type", typ)
                self.send_header("Content-Length", str(len(dane)))
                self.send_header("Cache-Control", "no-store" if typ.startswith("application/json") else "max-age=3600")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(dane)

            def _ok(self, q) -> bool:
                t = self.headers.get("X-Token") or q.get("t", [""])[0]
                return bool(t) and t in s.tokeny

            def do_GET(self):
                u = urlparse(self.path)
                q = parse_qs(u.query)
                if u.path in ("/", "/galeria"):
                    return self._wyslij((UI / "galeria.html").read_bytes(), "text/html; charset=utf-8")
                if u.path.startswith("/ui/"):
                    p = plik_ui(u.path)
                    return self._wyslij(*p) if p else self._wyslij(None)
                if not self._ok(q):
                    return self._wyslij({"blad": "Podaj PIN"}, kod=HTTPStatus.UNAUTHORIZED)
                try:
                    w = obsluz_api(s.galeria, u.path, q)
                except Exception as e:  # pragma: no cover - nie wywracamy serwera
                    return self._wyslij({"blad": str(e)}, kod=HTTPStatus.INTERNAL_SERVER_ERROR)
                if w is None:
                    return self._wyslij(None)
                if w[0] == "film":
                    return wyslij_strumien(self, w[1])
                return self._wyslij(w[0], w[1]) if w[1] else self._wyslij(w[0])

            def do_POST(self):
                u = urlparse(self.path)
                if u.path != "/api/g/zaloguj":
                    return self._wyslij(None)
                ip = self.client_address[0]
                teraz = time.time()
                proby = [t for t in s.nieudane.get(ip, []) if teraz - t < 300]
                if len(proby) >= 8:
                    return self._wyslij({"blad": "Za dużo prób — spróbuj za 5 minut."}, kod=HTTPStatus.TOO_MANY_REQUESTS)
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    pin = str(json.loads(self.rfile.read(min(n, 1000)) or b"{}").get("pin", "")).strip()
                except (ValueError, AttributeError):
                    pin = ""
                if pin and secrets.compare_digest(pin, s.pin):
                    t = secrets.token_urlsafe(24)
                    s.tokeny.add(t)
                    return self._wyslij({"t": t})
                time.sleep(1)
                s.nieudane[ip] = proby + [teraz]
                return self._wyslij({"blad": "Zły PIN"}, kod=HTTPStatus.UNAUTHORIZED)
        return H


def serwer_24h(folder: str, port: int = 8080, pin: str | None = None, baza: str | None = None,
               co_ile_h: float = 6.0) -> None:  # pragma: no cover - uruchamiane na Raspberry Pi
    """Tryb serwera: skanuje folder biblioteki (na starcie i co kilka godzin) i udostępnia galerię."""
    folder = os.path.abspath(folder)
    dane = Path(baza) if baza else Path.home() / ".katalogator-galeria"
    dane.mkdir(parents=True, exist_ok=True)
    plik_bazy = dane / "galeria.db"
    g = Galeria(plik_bazy, lambda: [folder], pamiec_min=dane / "miniatury")
    srv = SerwerGalerii(g, port=port, pin=pin).start()
    print(f"Galeria: {', '.join(srv.adresy())}  PIN: {srv.pin}", flush=True)
    while True:
        try:
            db = skaner.otworz_baze(plik_bazy)
            try:
                w = skaner.skanuj(folder, db, watki=4, wypisz=lambda *_: None)
                print(f"Skan: {w['wszystkie']} plików ({w['nowe_lub_zmienione']} nowych/zmienionych)", flush=True)
            finally:
                db.close()
        except Exception as e:
            print(f"Skan nieudany: {e}", flush=True)
        time.sleep(co_ile_h * 3600)
