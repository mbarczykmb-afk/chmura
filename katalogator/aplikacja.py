"""Aplikacja okienkowa: lokalny serwer + interfejs HTML w oknie Edge (tryb aplikacji).

Serwer słucha tylko na 127.0.0.1 i wymaga losowego tokenu, więc inne strony
ani komputery w sieci nie mają do niego dostępu.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__, analiza, duplikaty, dyski, planista, raport, skaner, wykonawca

UI = Path(__file__).parent / "ui"
BEZ_PINGU_ZAMKNIJ_PO = 150  # s; przeglądarka spowalnia timery w zminimalizowanym oknie


def katalog_danych() -> Path:
    baza = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    k = Path(baza) / "Katalogator"
    k.mkdir(parents=True, exist_ok=True)
    return k


class Stan:
    def __init__(self, katalog: Path):
        self.katalog = katalog
        self.plik_ustawien = katalog / "ustawienia.json"
        self.baza = katalog / "katalog.db"
        self.ustawienia = {"zrodla": [], "cel": ""}
        try:
            self.ustawienia.update(json.loads(self.plik_ustawien.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        self.ustawienia["zrodla"] = dyski.normalizuj_wybor(self.ustawienia.get("zrodla") or [])
        self.blokada = threading.Lock()
        self.przerwij = threading.Event()
        self.skan = {"trwa": False, "przejrzano": 0, "folder": "", "komunikat": "", "blad": ""}
        self.dup = {"trwa": False, "etap": "", "zrobione": 0, "wszystkie": 0, "bajty": 0,
                    "komunikat": "", "blad": ""}
        self.zad = {n: self._pusty() for n in ("analiza", "plan", "wykonanie")}
        self.miniatury: dict[int, bytes] = {}
        self.ostatni_ping = time.time()

    @staticmethod
    def _pusty() -> dict:
        return {"trwa": False, "etap": "", "zrobione": 0, "wszystkie": 0, "bajty": 0, "komunikat": "", "blad": ""}

    def zapisz_ustawienia(self, dane: dict) -> None:
        zrodla = dyski.normalizuj_wybor(dane.get("zrodla") or [])
        cel = str(dane.get("cel", "")).strip()
        self.ustawienia = {"zrodla": zrodla, "cel": os.path.normpath(cel) if cel else ""}
        self.plik_ustawien.write_text(json.dumps(self.ustawienia, ensure_ascii=False, indent=2), encoding="utf-8")

    def ma_wyniki(self) -> bool:
        if not self.baza.exists():
            return False
        db = skaner.otworz_baze(self.baza)
        try:
            return db.execute("SELECT 1 FROM pliki LIMIT 1").fetchone() is not None
        finally:
            db.close()

    def db(self):
        db = skaner.otworz_baze(self.baza)
        wykonawca.przygotuj(db)  # tworzy też tabele duplikatów, analizy i planu
        return db

    def stan(self) -> dict:
        with self.blokada:
            skan, dup = dict(self.skan), dict(self.dup)
        ma = self.ma_wyniki()
        with self.blokada:
            zad = {k: dict(v) for k, v in self.zad.items()}
        dane = {"wersja": __version__, "windows": dyski.WINDOWS, "sep": os.sep, **self.ustawienia, "skan": skan,
                "dup": dup, "zad": zad, "ma_wyniki": ma, "duplikaty": None, "do_cofniecia": None,
                "analiza": None, "plan": None, "wykonanie": None}
        if ma:
            db = self.db()
            try:
                if db.execute("SELECT 1 FROM odciski LIMIT 1").fetchone():
                    dane["duplikaty"] = duplikaty.podsumowanie(db)
                dane["do_cofniecia"] = duplikaty.ostatnia_partia(db)
                if db.execute("SELECT 1 FROM analiza LIMIT 1").fetchone():
                    dane["analiza"] = analiza.podsumowanie(db)
                if planista.istnieje(db):
                    dane["plan"] = planista.podsumowanie(db)
                dane["wykonanie"] = wykonawca.ostatnia_partia(db)
            finally:
                db.close()
        return dane

    def _zajety(self) -> bool:  # wywoływać pod blokadą
        return self.skan["trwa"] or self.dup["trwa"] or any(z["trwa"] for z in self.zad.values())

    def zajety(self) -> bool:
        with self.blokada:
            return self._zajety()

    def uruchom(self, nazwa: str, funkcja) -> str | None:
        """Zadanie w tle: funkcja(db, postep, przerwij) -> komunikat."""
        with self.blokada:
            if self._zajety():
                return "Poczekaj, aż skończy się bieżące zadanie."
            self.zad[nazwa] = {**self._pusty(), "trwa": True, "etap": "przygotowanie"}
        self.przerwij.clear()

        def praca():
            db = self.db()

            def postep(etap, zrobione, wszystkie, bajty):
                with self.blokada:
                    self.zad[nazwa].update(etap=etap, zrobione=zrobione, wszystkie=wszystkie, bajty=bajty)
            try:
                komunikat, blad = funkcja(db, postep, self.przerwij), ""
            except skaner.Przerwano:
                komunikat, blad = "Przerwano. Postęp zapisany — możesz dokończyć później.", ""
            except Exception as e:
                komunikat, blad = "Nie powiodło się.", f"{e}" if isinstance(e, (OSError, ValueError)) else \
                    f"{type(e).__name__}: {e}"
            finally:
                db.close()
            with self.blokada:
                self.zad[nazwa].update(trwa=False, komunikat=komunikat, blad=blad)

        threading.Thread(target=praca, daemon=True).start()
        return None

    # --- skan w tle ----------------------------------------------------
    def rozpocznij_skan(self) -> str | None:
        foldery = [z["sciezka"] for z in self.ustawienia["zrodla"]]
        cel = self.ustawienia["cel"]
        if cel and not any(dyski.zawiera(z, cel) for z in foldery):
            foldery.append(cel)  # miejsce docelowe też skanujemy (o ile nie leży w źródle)
        if not foldery:
            return "Najpierw wybierz folder do uporządkowania."
        brak = [f for f in foldery if not os.path.isdir(f)]
        if brak:
            return "Nie mogę otworzyć folderu: " + ", ".join(brak)
        with self.blokada:
            if self._zajety():
                return "Poczekaj, aż skończy się bieżące zadanie."
            self.skan = {"trwa": True, "przejrzano": 0, "folder": "", "komunikat": "Rozpoczynam…", "blad": ""}
        self.przerwij.clear()
        threading.Thread(target=self._skanuj, args=(foldery,), daemon=True).start()
        return None

    def _skanuj(self, foldery: list[str]) -> None:
        db = skaner.otworz_baze(self.baza)
        razem = 0
        try:
            for i, folder in enumerate(foldery, 1):
                def postep(n, gdzie, _i=i, _baza=razem):
                    with self.blokada:
                        self.skan.update(przejrzano=_baza + n, folder=gdzie,
                                         komunikat=f"Folder {_i} z {len(foldery)}")
                w = skaner.skanuj(folder, db, postep=postep, przerwij=self.przerwij)
                razem += w["wszystkie"]
            komunikat, blad = f"Gotowe — przejrzano {razem} plików.", ""
        except skaner.Przerwano:
            komunikat, blad = "Przerwano. Postęp zapisany — kolejny skan dokończy resztę.", ""
        except Exception as e:  # pokaż błąd w oknie zamiast cichej awarii
            komunikat, blad = "Skan nie powiódł się.", f"{type(e).__name__}: {e}"
        finally:
            db.close()
        with self.blokada:
            self.skan.update(trwa=False, komunikat=komunikat, blad=blad)

    # --- duplikaty w tle --------------------------------------------------
    def szukaj_duplikatow(self) -> str | None:
        if not self.ma_wyniki():
            return "Najpierw zeskanuj foldery."
        with self.blokada:
            if self._zajety():
                return "Poczekaj, aż skończy się bieżące zadanie."
            self.dup = {"trwa": True, "etap": "przygotowanie", "zrobione": 0, "wszystkie": 0, "bajty": 0,
                        "komunikat": "", "blad": ""}
        self.przerwij.clear()
        threading.Thread(target=self._duplikaty, daemon=True).start()
        return None

    def _duplikaty(self) -> None:
        db = self.db()

        def postep(etap, zrobione, wszystkie, bajty):
            with self.blokada:
                self.dup.update(etap=etap, zrobione=zrobione, wszystkie=wszystkie, bajty=bajty)
        try:
            w = duplikaty.szukaj(db, postep=postep, przerwij=self.przerwij)
            komunikat, blad = (f"Znaleziono {w['nadmiar']} zbędnych kopii "
                               f"({raport.rozmiar_txt(w['bajty'])})." if w["nadmiar"]
                               else "Nie znaleziono duplikatów."), ""
        except skaner.Przerwano:
            komunikat, blad = "Przerwano. Sprawdzone pliki są zapamiętane.", ""
        except Exception as e:
            komunikat, blad = "Wyszukiwanie nie powiodło się.", f"{type(e).__name__}: {e}"
        finally:
            db.close()
        with self.blokada:
            self.dup.update(trwa=False, komunikat=komunikat, blad=blad)

    def grupy(self, rodzaj: str | None, od: int, ile: int) -> dict:
        db = self.db()
        try:
            cele = {os.path.abspath(self.ustawienia["cel"])} if self.ustawienia["cel"] else set()
            return {"grupy": duplikaty.grupy(db, rodzaj or None, od, ile, cele),
                    "podsumowanie": duplikaty.podsumowanie(db)}
        finally:
            db.close()

    def przenies_duplikaty(self, decyzje: list) -> dict:
        if self.zajety():
            return {"blad": "Poczekaj, aż skończy się bieżące zadanie."}
        db = self.db()
        try:
            return duplikaty.przenies(db, decyzje)
        finally:
            db.close()

    def cofnij(self) -> dict:
        if self.zajety():
            return {"blad": "Poczekaj, aż skończy się bieżące zadanie."}
        db = self.db()
        try:
            return duplikaty.cofnij(db)
        finally:
            db.close()

    def miniatura(self, id_: int) -> bytes | None:
        if id_ in self.miniatury:
            return self.miniatury[id_]
        db = self.db()
        try:
            r = db.execute("SELECT sciezka FROM pliki WHERE rowid=? AND rodzaj='zdjecie'", (id_,)).fetchone()
            if not r:  # plik z planu, którego nie ma już w skanie (np. w miejscu docelowym)
                r = db.execute("SELECT sciezka FROM plan WHERE plik_id=? AND rodzaj='zdjecie'", (id_,)).fetchone()
        finally:
            db.close()
        if not r:
            return None
        try:
            import io
            im, _ = analiza.miniatura(r["sciezka"], min_bok=150)
            im.thumbnail((260, 260))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=82)
        except Exception:
            return None
        if len(self.miniatury) > 600:
            self.miniatury.clear()
        self.miniatury[id_] = buf.getvalue()
        return self.miniatury[id_]

    # --- zadania: analiza, plan, wykonanie ---------------------------------------
    def analizuj(self) -> str | None:
        if not self.ma_wyniki():
            return "Najpierw zeskanuj foldery."

        def f(db, postep, przerwij):
            w = analiza.analizuj(db, postep=postep, przerwij=przerwij)
            return (f"Przeanalizowano {w['przeanalizowane']} zdjęć: możliwych dokumentów {w['dokumenty']}, "
                    f"grup podobnych {w['podobne_grupy']}.")
        return self.uruchom("analiza", f)

    def generuj_plan(self) -> str | None:
        if not self.ma_wyniki():
            return "Najpierw zeskanuj foldery."
        if not self.ustawienia["cel"]:
            return "Najpierw wybierz miejsce docelowe („Dokąd?”)."
        zrodla, cel = list(self.ustawienia["zrodla"]), self.ustawienia["cel"]

        def f(db, postep, przerwij):
            w = planista.generuj(db, zrodla, cel, postep=postep, przerwij=przerwij)
            return f"Propozycja gotowa: {w['kopiuj'] + w['przenies']} plików do uporządkowania."
        return self.uruchom("plan", f)

    def wykonaj(self, usun_puste: bool) -> str | None:
        def f(db, postep, przerwij):
            w = wykonawca.wykonaj(db, postep=postep, przerwij=przerwij, usun_puste=usun_puste)
            k = f"Gotowe: {w['zrobione']} plików ({raport.rozmiar_txt(w['bajty'])})."
            if w["bledy"]:
                k += f" Błędy: {w['bledy']} — szczegóły w drzewie (czerwone)."
            if w["usuniete_foldery"]:
                k += f" Usunięto pustych folderów: {w['usuniete_foldery']}."
            return k
        return self.uruchom("wykonanie", f)

    def cofnij_wykonanie(self) -> str | None:
        def f(db, postep, przerwij):
            w = wykonawca.cofnij(db, postep=postep, przerwij=przerwij)
            k = f"Cofnięto {w['cofniete']} plików. Przeskanuj foldery, żeby odświeżyć wyniki."
            if w["bledy"]:
                k += " Problemy: " + "; ".join(w["bledy"][:5])
            return k
        return self.uruchom("wykonanie", f)

    def z_db(self, funkcja, *a, **kw):
        db = self.db()
        try:
            return funkcja(db, *a, **kw)
        finally:
            db.close()

    def raport_html(self) -> str:
        db = skaner.otworz_baze(self.baza)
        try:
            return raport.html_raport(raport.zbierz(db))
        finally:
            db.close()


def _handler(stan: Stan, token: str, zamknij):
    class H(BaseHTTPRequestHandler):
        server_version = "Katalogator"

        def log_message(self, *a):  # bez wypisywania do konsoli (aplikacja okienkowa)
            pass

        def _ok_token(self, q) -> bool:
            return secrets.compare_digest(self.headers.get("X-Token") or q.get("t", [""])[0], token)

        def _wyslij(self, tresc, typ="application/json; charset=utf-8", kod=HTTPStatus.OK):
            if not isinstance(tresc, (bytes, str)):
                tresc = json.dumps(tresc, ensure_ascii=False)
            dane = tresc.encode("utf-8") if isinstance(tresc, str) else tresc
            self.send_response(kod)
            self.send_header("Content-Type", typ)
            self.send_header("Content-Length", str(len(dane)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(dane)

        def _json(self) -> dict:
            dl = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(dl) or b"{}")
            except ValueError:
                return {}

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path in ("/", "/index.html"):
                if not self._ok_token(q):
                    return self._wyslij("Brak dostępu", "text/plain; charset=utf-8", HTTPStatus.FORBIDDEN)
                return self._wyslij((UI / "index.html").read_bytes(), "text/html; charset=utf-8")
            if not u.path.startswith("/ui/") and not self._ok_token(q):
                return self._wyslij({"blad": "brak dostępu"}, kod=HTTPStatus.FORBIDDEN)
            if not u.path.startswith("/ui/"):
                stan.ostatni_ping = time.time()
            if u.path == "/api/stan":
                return self._wyslij(stan.stan())
            if u.path == "/raport":
                return self._wyslij(stan.raport_html(), "text/html; charset=utf-8")
            if u.path.startswith("/ui/") and u.path.endswith((".js", ".css")):
                plik = UI / os.path.basename(u.path)
                if plik.is_file():
                    return self._wyslij(plik.read_bytes(), "text/javascript; charset=utf-8"
                                        if plik.suffix == ".js" else "text/css; charset=utf-8")
                return self._wyslij(b"", "text/plain", HTTPStatus.NOT_FOUND)
            if u.path == "/api/plan/drzewo":
                return self._wyslij({"foldery": stan.z_db(planista.drzewo),
                                     "podsumowanie": stan.z_db(planista.podsumowanie)})
            if u.path == "/api/plan/pliki":
                return self._wyslij(stan.z_db(planista.pliki_folderu, q.get("folder", [""])[0],
                                              _int(q, "od", 0), min(_int(q, "ile", 200), 500)))
            if u.path == "/api/plan/sprawdz":
                return self._wyslij(stan.z_db(wykonawca.sprawdz))
            if u.path == "/api/dokumenty":
                return self._wyslij({"kandydaci": stan.z_db(analiza.kandydaci_dokumentow)})
            if u.path == "/api/podobne":
                grupy = stan.z_db(analiza.grupy_podobnych)
                od, ile = _int(q, "od", 0), min(_int(q, "ile", 30), 200)
                return self._wyslij({"razem": len(grupy), "grupy": [
                    [{k: w[k] for k in ("id", "sciezka", "wzgledna", "mtime", "rozmiar", "szer", "wys", "ostrosc")}
                     for w in g] for g in grupy[od:od + ile]]})
            if u.path == "/api/nieostre":
                return self._wyslij({"pliki": stan.z_db(analiza.najmniej_ostre, min(_int(q, "ile", 120), 500))})
            if u.path == "/api/dyski":
                return self._wyslij({"dyski": dyski.lista_dyskow()})
            if u.path == "/api/foldery":
                return self._wyslij(dyski.podfoldery(q.get("sciezka", [""])[0]))
            if u.path == "/api/duplikaty":
                try:
                    od, ile = int(q.get("od", ["0"])[0]), min(int(q.get("ile", ["40"])[0]), 200)
                except ValueError:
                    od, ile = 0, 40
                return self._wyslij(stan.grupy(q.get("rodzaj", [""])[0], od, ile))
            if u.path == "/miniatura":
                try:
                    dane = stan.miniatura(int(q.get("id", ["0"])[0]))
                except ValueError:
                    dane = None
                if dane is None:
                    return self._wyslij(b"", "image/jpeg", HTTPStatus.NOT_FOUND)
                return self._wyslij(dane, "image/jpeg")
            self._wyslij({"blad": "nie ma"}, kod=HTTPStatus.NOT_FOUND)

        def do_POST(self):
            u = urlparse(self.path)
            if not self._ok_token(parse_qs(u.query)):
                return self._wyslij({"blad": "brak dostępu"}, kod=HTTPStatus.FORBIDDEN)
            stan.ostatni_ping = time.time()
            dane = self._json()
            if u.path == "/api/ustawienia":
                stan.zapisz_ustawienia(dane)
                return self._wyslij(stan.stan())
            if u.path == "/api/nowy-folder":
                w = dyski.nowy_folder(str(dane.get("w", "")), str(dane.get("nazwa", "")))
                return self._wyslij(w, kod=HTTPStatus.BAD_REQUEST if "blad" in w else HTTPStatus.OK)
            if u.path == "/api/skanuj":
                blad = stan.rozpocznij_skan()
                return self._wyslij({"blad": blad} if blad else stan.stan(),
                                    kod=HTTPStatus.BAD_REQUEST if blad else HTTPStatus.OK)
            if u.path == "/api/duplikaty/szukaj":
                blad = stan.szukaj_duplikatow()
                return self._wyslij({"blad": blad} if blad else stan.stan(),
                                    kod=HTTPStatus.BAD_REQUEST if blad else HTTPStatus.OK)
            if u.path == "/api/duplikaty/przenies":
                w = stan.przenies_duplikaty(dane.get("decyzje") or [])
                return self._wyslij(w, kod=HTTPStatus.BAD_REQUEST if "blad" in w else HTTPStatus.OK)
            if u.path == "/api/duplikaty/cofnij":
                w = stan.cofnij()
                return self._wyslij(w, kod=HTTPStatus.BAD_REQUEST if "blad" in w else HTTPStatus.OK)
            proste = {
                "/api/analiza/start": lambda: stan.analizuj(),
                "/api/plan/generuj": lambda: stan.generuj_plan(),
                "/api/wykonaj": lambda: stan.wykonaj(bool(dane.get("usun_puste", True))),
                "/api/wykonanie/cofnij": lambda: stan.cofnij_wykonanie(),
            }
            if u.path in proste:
                blad = proste[u.path]()
                return self._wyslij({"blad": blad} if blad else stan.stan(),
                                    kod=HTTPStatus.BAD_REQUEST if blad else HTTPStatus.OK)
            edycja = {
                "/api/plan/zmien-nazwe": lambda db: planista.zmien_nazwe_folderu(db, str(dane.get("stara", "")),
                                                                                   str(dane.get("nowa", ""))),
                "/api/plan/przenies": lambda db: planista.przenies_pliki(db, [int(i) for i in dane.get("ids") or []],
                                                                         str(dane.get("folder", ""))),
                "/api/plan/wyklucz": lambda db: planista.wyklucz(
                    db, [int(i) for i in dane.get("ids") or []] if "ids" in dane else None,
                    dane.get("folder"), bool(dane.get("wartosc", True))),
                "/api/plan/cofnij": planista.cofnij,
                "/api/plan/ponow": planista.ponow,
                "/api/dokumenty/zapisz": lambda db: {
                    **analiza.zapisz_decyzje(db, [int(i) for i in dane.get("tak") or []],
                                             [int(i) for i in dane.get("nie") or []]),
                    "plan": planista.oznacz_dokumenty(db, analiza.dokumenty_potwierdzone(db))},
                "/api/odloz": lambda db: duplikaty.odloz(db, [int(i) for i in dane.get("ids") or []],
                                                         "podobne" if dane.get("typ") == "podobne" else "nieostre"),
            }
            if u.path in edycja:
                if u.path == "/api/odloz" and stan.zajety():
                    return self._wyslij({"blad": "Poczekaj, aż skończy się bieżące zadanie."}, kod=HTTPStatus.BAD_REQUEST)
                w = stan.z_db(edycja[u.path])
                return self._wyslij(w, kod=HTTPStatus.BAD_REQUEST if "blad" in w else HTTPStatus.OK)
            if u.path == "/api/przerwij":
                stan.przerwij.set()
                return self._wyslij({"ok": True})
            if u.path == "/api/zamknij":
                self._wyslij({"ok": True})
                stan.przerwij.set()
                threading.Thread(target=zamknij, daemon=True).start()
                return None
            self._wyslij({"blad": "nie ma"}, kod=HTTPStatus.NOT_FOUND)

    return H


def _int(q: dict, klucz: str, domyslnie: int) -> int:
    try:
        return int(q.get(klucz, [domyslnie])[0])
    except (TypeError, ValueError):
        return domyslnie


def uruchom_serwer(katalog: Path | None = None, port: int = 0):
    """Zwraca (serwer, adres_url, stan). Serwer trzeba obsłużyć: serve_forever()."""
    stan = Stan(katalog or katalog_danych())
    token = secrets.token_urlsafe(24)
    serwer: ThreadingHTTPServer | None = None

    def zamknij():
        if serwer is not None:
            serwer.shutdown()

    serwer = ThreadingHTTPServer(("127.0.0.1", port), _handler(stan, token, zamknij))
    serwer.daemon_threads = True
    url = f"http://127.0.0.1:{serwer.server_address[1]}/?t={token}"
    return serwer, url, stan


def otworz_okno(url: str) -> None:
    """Edge/Chrome w trybie aplikacji (okno bez paska adresu), inaczej domyślna przeglądarka."""
    kandydaci = []
    if sys.platform == "win32":
        for zm in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
            baza = os.environ.get(zm)
            if baza:
                kandydaci += [Path(baza) / "Microsoft/Edge/Application/msedge.exe",
                              Path(baza) / "Google/Chrome/Application/chrome.exe"]
    else:
        kandydaci += [Path(p) for p in filter(None, (shutil.which("microsoft-edge"),
                                                     shutil.which("google-chrome"),
                                                     shutil.which("chromium")))]
    for exe in kandydaci:
        if exe.exists():
            try:
                subprocess.Popen([str(exe), f"--app={url}", "--window-size=1180,860"])
                return
            except OSError:
                continue
    webbrowser.open(url)


def main(otworz: bool = True) -> None:
    serwer, url, stan = uruchom_serwer()

    def pilnuj():  # zamknięcie okna = koniec programu (skan jest wznawialny)
        while True:
            time.sleep(10)
            if time.time() - stan.ostatni_ping > BEZ_PINGU_ZAMKNIJ_PO:
                stan.przerwij.set()
                serwer.shutdown()
                return

    threading.Thread(target=pilnuj, daemon=True).start()
    if otworz:
        otworz_okno(url)
    try:
        serwer.serve_forever()
    finally:
        serwer.server_close()


if __name__ == "__main__":
    main()
