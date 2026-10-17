"""👤 Osoby: wykrywanie twarzy na zdjęciach i grupowanie ich w osoby — w całości na komputerze, bez chmury.

Wykrywanie: YuNet (OpenCV, model 230 KB w programie). Rozpoznawanie: SFace (model 38 MB, pobierany raz
z oficjalnego repozytorium OpenCV przy pierwszym użyciu). Dla każdej twarzy zapisujemy wektor cech
i mały wycinek (miniaturę twarzy); twarze o podobnych wektorach łączymy w osoby. Imię nadajesz Ty —
potem zdjęcia danej osoby znajdziesz w widoku „Osoby” albo wpisując imię w wyszukiwarkę.
Dane trzymamy w bazie oglądanej galerii (projektu albo Przeglądarki), obok ulubionych i albumów."""
from __future__ import annotations

import hashlib
import io
import logging
import os
import threading
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps

from . import skaner

LOG = logging.getLogger("katalogator.twarze")

DANE = Path(__file__).with_name("dane") / "twarze"
MODEL_WYKRYWANIA = DANE / "face_detection_yunet_2023mar.onnx"
MODEL_ROZPOZNAWANIA = "face_recognition_sface_2021dec.onnx"
URL_ROZPOZNAWANIA = ("https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
                     "face_recognition_sface/face_recognition_sface_2021dec.onnx")
SHA_ROZPOZNAWANIA = "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"
KATALOG_MODELI: Path | None = None  # <dane programu>/modele — ustawia aplikacja

BOK = 1280          # zdjęcie zmniejszamy do tylu pikseli (szybko, a twarze zostają czytelne)
MIN_TWARZ = 36      # mniejsze twarze (tłum w tle) pomijamy — i tak nie da się ich rozpoznać
PEWNOSC = 0.86      # próg wykrywania YuNet
PODOBNE = 0.40      # cosinus z średnią osoby: od tylu „to ta sama osoba” (SFace: 0.363 = ta sama tożsamość)

SCHEMAT = """
CREATE TABLE IF NOT EXISTS g_twarze_pliki (sciezka TEXT PRIMARY KEY, mtime REAL NOT NULL, n INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS g_osoby (id INTEGER PRIMARY KEY AUTOINCREMENT, nazwa TEXT NOT NULL DEFAULT '',
                                    ukryta INTEGER NOT NULL DEFAULT 0, okladka INTEGER);
CREATE TABLE IF NOT EXISTS g_twarze (id INTEGER PRIMARY KEY AUTOINCREMENT, sciezka TEXT NOT NULL,
                                     x REAL, y REAL, w REAL, h REAL, wynik REAL, wektor BLOB NOT NULL,
                                     osoba INTEGER, reczna INTEGER NOT NULL DEFAULT 0, miniatura BLOB);
CREATE INDEX IF NOT EXISTS g_twarze_sciezka ON g_twarze(sciezka);
CREATE INDEX IF NOT EXISTS g_twarze_osoba ON g_twarze(osoba);
"""

_STANY: dict[str, dict] = {}   # baza → stan zadania (jedno wykrywanie na bazę naraz)
_BLOKADA = threading.Lock()


def dostepne() -> str | None:
    """None, gdy można wykrywać; inaczej powód (brak OpenCV)."""
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        return "Brak modułu OpenCV — zainstaluj nową wersję Katalogatora."
    return None


def przygotuj(db) -> None:
    db.executescript(SCHEMAT)


def _plik_modelu() -> Path:
    return Path(KATALOG_MODELI or Path.home() / ".katalogator" / "modele") / MODEL_ROZPOZNAWANIA


def pobierz_model(postep=lambda *_: None) -> Path:
    """Model rozpoznawania (38 MB) — raz, z oficjalnego repozytorium OpenCV; sprawdzamy sumę SHA-256."""
    cel = _plik_modelu()
    if cel.is_file():
        return cel
    cel.parent.mkdir(parents=True, exist_ok=True)
    tmp = cel.with_suffix(".pobieranie")
    h = hashlib.sha256()
    with urllib.request.urlopen(URL_ROZPOZNAWANIA, timeout=60) as r, open(tmp, "wb") as f:
        razem, n = int(r.headers.get("Content-Length") or 0), 0
        while True:
            k = r.read(1 << 20)
            if not k:
                break
            f.write(k); h.update(k); n += len(k)
            postep(n, razem)
    if h.hexdigest() != SHA_ROZPOZNAWANIA:
        tmp.unlink(missing_ok=True)
        raise OSError("pobrany model ma złą sumę kontrolną")
    os.replace(tmp, cel)
    return cel


def _obraz(sciezka: str):
    """Zdjęcie jako tablica BGR (OpenCV), zmniejszone do BOK, z obrotem z EXIF."""
    import numpy as np
    with Image.open(sciezka) as im:
        try:
            im.draft("RGB", (BOK, BOK))  # JPEG: dekodowanie od razu w mniejszej skali — kilka razy szybciej
        except Exception:  # noqa: BLE001
            pass
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((BOK, BOK))
        return np.ascontiguousarray(np.asarray(im)[:, :, ::-1]), im


class _Silnik:
    def __init__(self, model_rozp: Path):
        import cv2
        self.cv2 = cv2
        self.det = cv2.FaceDetectorYN.create(str(MODEL_WYKRYWANIA), "", (320, 320), PEWNOSC, 0.3, 50)
        self.rec = cv2.FaceRecognizerSF.create(str(model_rozp), "")

    def twarze(self, sciezka: str) -> list[dict]:
        import numpy as np
        bgr, rgb = _obraz(sciezka)
        h, w = bgr.shape[:2]
        self.det.setInputSize((w, h))
        _, wyn = self.det.detect(bgr)
        out = []
        for f in (wyn if wyn is not None else []):
            x, y, fw, fh = (float(v) for v in f[:4])
            if min(fw, fh) < MIN_TWARZ:
                continue
            cecha = self.rec.feature(self.rec.alignCrop(bgr, f)).flatten().astype(np.float32)
            cecha /= (np.linalg.norm(cecha) or 1.0)
            m = max(fw, fh) * 0.25  # wycinek z marginesem — miniatura w widoku „Osoby”
            wyc = rgb.crop((max(0, int(x - m)), max(0, int(y - m)), min(w, int(x + fw + m)), min(h, int(y + fh + m))))
            wyc.thumbnail((160, 160))
            buf = io.BytesIO(); wyc.save(buf, "JPEG", quality=85)
            out.append({"x": x / w, "y": y / h, "w": fw / w, "h": fh / h, "wynik": float(f[14]),
                        "wektor": cecha.tobytes(), "miniatura": buf.getvalue()})
        return out


def stan(baza) -> dict:
    with _BLOKADA:
        return dict(_STANY.get(str(baza)) or {"trwa": False})


def przerwij(baza) -> None:
    with _BLOKADA:
        s = _STANY.get(str(baza))
        if s:
            s["przerwij"] = True


def start(galeria) -> str | None:
    """Wykrywanie twarzy w tle na zdjęciach z zakresu galerii, których jeszcze nie przejrzano (albo zmienionych)."""
    powod = dostepne()
    if powod:
        return powod
    k = str(galeria.baza)
    with _BLOKADA:
        if (_STANY.get(k) or {}).get("trwa"):
            return None  # już trwa
        _STANY[k] = {"trwa": True, "zrobione": 0, "wszystkie": 0, "twarzy": 0, "komunikat": "Przygotowuję…",
                     "blad": "", "przerwij": False, "start": time.time()}
    threading.Thread(target=_praca, args=(galeria,), daemon=True, name="twarze").start()
    return None


def _ustaw(k: str, **z) -> bool:
    with _BLOKADA:
        s = _STANY[k]
        s.update(z)
        return not s.get("przerwij")


def _praca(galeria) -> None:
    k = str(galeria.baza)
    try:
        try:
            model = pobierz_model(lambda n, r: _ustaw(k, komunikat=f"Pobieram model rozpoznawania twarzy (raz): "
                                                         f"{n // 1048576} z {max(1, r // 1048576)} MB"))
        except OSError as e:
            _ustaw(k, trwa=False, blad=f"Nie udało się pobrać modelu rozpoznawania twarzy ({e}). "
                                       "Sprawdź internet i spróbuj ponownie — potrzebny tylko raz.")
            return
        silnik = _Silnik(model)
        db = galeria._db()
        try:
            przygotuj(db)
            w, arg = galeria._warunek()
            znane = {r[0]: r[1] for r in db.execute("SELECT sciezka, mtime FROM g_twarze_pliki")}
            do_zrobienia = [(r[0], r[1]) for r in db.execute(
                f"SELECT sciezka, mtime FROM pliki WHERE rodzaj='zdjecie' {w} ORDER BY data DESC", arg)
                if znane.get(r[0]) is None or abs((znane.get(r[0]) or 0) - (r[1] or 0)) > 1]
            _ustaw(k, wszystkie=len(do_zrobienia), komunikat="Szukam twarzy na zdjęciach…")
            twarzy, ostatni_zapis = 0, time.time()
            for i, (sc, mt) in enumerate(do_zrobienia, 1):
                try:
                    lista = silnik.twarze(sc)
                except Exception as e:  # noqa: BLE001 — uszkodzony / nieobsługiwany plik: pomijamy
                    LOG.debug("twarze: %s — %s", sc, e)
                    lista = []
                db.execute("DELETE FROM g_twarze WHERE sciezka=? AND reczna=0", (sc,))
                for t in lista:
                    db.execute("INSERT INTO g_twarze (sciezka, x, y, w, h, wynik, wektor, miniatura) VALUES (?,?,?,?,?,?,?,?)",
                               (sc, t["x"], t["y"], t["w"], t["h"], t["wynik"], t["wektor"], t["miniatura"]))
                db.execute("INSERT OR REPLACE INTO g_twarze_pliki VALUES (?,?,?)", (sc, mt or 0, len(lista)))
                twarzy += len(lista)
                if time.time() - ostatni_zapis > 3 or i == len(do_zrobienia):
                    db.commit(); ostatni_zapis = time.time()
                    grupuj(db)
                if not _ustaw(k, zrobione=i, twarzy=twarzy):
                    db.commit(); grupuj(db)
                    _ustaw(k, trwa=False, komunikat="Przerwano — znalezione osoby już są widoczne.")
                    return
            db.commit()
            grupuj(db)
            _ustaw(k, trwa=False, komunikat=f"Gotowe — przejrzano {len(do_zrobienia)} zdjęć, nowych twarzy: {twarzy}.")
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        LOG.exception("twarze: błąd")
        _ustaw(k, trwa=False, blad=str(e))


def grupuj(db) -> int:
    """Twarze bez osoby → do najbardziej podobnej osoby (średni wektor) albo nowa osoba. Zwraca liczbę przypisanych.
    Twarze odłączone ręcznie (reczna=1, osoba NULL) zostają bez osoby."""
    import numpy as np
    nowe = db.execute("SELECT id, wektor FROM g_twarze WHERE osoba IS NULL AND reczna=0 ORDER BY id").fetchall()
    if not nowe:
        return 0
    srodki: dict[int, list] = {}  # osoba → [suma wektorów, liczba]
    for o, v in db.execute("SELECT osoba, wektor FROM g_twarze WHERE osoba IS NOT NULL"):
        s = srodki.setdefault(o, [np.zeros(128, np.float32), 0])
        s[0] += np.frombuffer(v, np.float32); s[1] += 1
    ids = list(srodki)
    macierz = np.array([srodki[o][0] / (np.linalg.norm(srodki[o][0]) or 1) for o in ids], np.float32).reshape(-1, 128)
    for tid, v in nowe:
        wek = np.frombuffer(v, np.float32)
        o = None
        if len(ids):
            pod = macierz @ wek
            j = int(pod.argmax())
            if pod[j] >= PODOBNE:
                o = ids[j]
        if o is None:
            o = db.execute("INSERT INTO g_osoby (nazwa) VALUES ('')").lastrowid
            srodki[o] = [np.zeros(128, np.float32), 0]
            ids.append(o)
            macierz = np.vstack([macierz, np.zeros((1, 128), np.float32)])
        s = srodki[o]
        s[0] += wek; s[1] += 1
        macierz[ids.index(o)] = s[0] / (np.linalg.norm(s[0]) or 1)
        db.execute("UPDATE g_twarze SET osoba=? WHERE id=?", (o, tid))
    db.commit()
    return len(nowe)


# --- dane dla widoku „Osoby” --------------------------------------------------------------------------------
def osoby(galeria, wszystkie: bool = False) -> dict:
    db = galeria._db()
    try:
        przygotuj(db)
        w, arg = galeria._warunek()
        wiersze = db.execute(
            f"""SELECT o.id, o.nazwa, o.ukryta, o.okladka, COUNT(DISTINCT t.sciezka) n,
                       (SELECT id FROM g_twarze WHERE osoba=o.id ORDER BY wynik DESC LIMIT 1) najlepsza
                FROM g_osoby o JOIN g_twarze t ON t.osoba = o.id
                WHERE t.sciezka IN (SELECT sciezka FROM pliki WHERE rodzaj='zdjecie' {w})
                GROUP BY o.id ORDER BY (o.nazwa != '') DESC, n DESC""", arg).fetchall()
        przejrzane = db.execute("SELECT COUNT(*) FROM g_twarze_pliki").fetchone()[0]
        zdjec = db.execute(f"SELECT COUNT(*) FROM pliki WHERE rodzaj='zdjecie' {w}", arg).fetchone()[0]
    finally:
        db.close()
    lista = [{"id": r["id"], "nazwa": r["nazwa"], "n": r["n"], "ukryta": bool(r["ukryta"]),
              "twarz": r["okladka"] or r["najlepsza"]} for r in wiersze]
    widoczne = [o for o in lista if not o["ukryta"] and (o["nazwa"] or o["n"] >= 2)]
    return {"osoby": lista if wszystkie else widoczne, "pozostale": len(lista) - len(widoczne),
            "przejrzane": przejrzane, "zdjec": zdjec, "stan": stan(galeria.baza), "niedostepne": dostepne()}


def miniatura_twarzy(galeria, id_: int) -> bytes | None:
    db = galeria._db()
    try:
        przygotuj(db)
        r = db.execute("SELECT miniatura FROM g_twarze WHERE id=?", (int(id_),)).fetchone()
    finally:
        db.close()
    return r[0] if r else None


def twarze_pliku(galeria, id_: int) -> dict:
    sc = galeria.sciezka(id_, "zdjecie")
    if not sc:
        return {"twarze": []}
    db = galeria._db()
    try:
        przygotuj(db)
        t = [dict(r) for r in db.execute(
            "SELECT t.id, t.x, t.y, t.w, t.h, t.osoba, coalesce(o.nazwa, '') nazwa FROM g_twarze t "
            "LEFT JOIN g_osoby o ON o.id = t.osoba WHERE t.sciezka=? ORDER BY t.x", (sc,))]
    finally:
        db.close()
    return {"twarze": t}


def sciezki_osoby_sql() -> str:
    return "SELECT sciezka FROM g_twarze WHERE osoba=?"


def nazwij(galeria, osoba: int, nazwa: str) -> dict:
    nazwa = " ".join(str(nazwa).split())[:60]
    db = galeria._db()
    try:
        przygotuj(db)
        # to samo imię co inna osoba = ta sama osoba — łączymy
        inna = db.execute("SELECT id FROM g_osoby WHERE lower(nazwa)=lower(?) AND id != ? AND nazwa != ''",
                          (nazwa, int(osoba))).fetchone() if nazwa else None
        if inna:
            db.execute("UPDATE g_twarze SET osoba=? WHERE osoba=?", (inna[0], int(osoba)))
            db.execute("DELETE FROM g_osoby WHERE id=?", (int(osoba),))
            db.commit()
            return {"ok": True, "polaczono": inna[0]}
        db.execute("UPDATE g_osoby SET nazwa=? WHERE id=?", (nazwa, int(osoba)))
        db.commit()
    finally:
        db.close()
    return {"ok": True}


def polacz(galeria, ids: list[int]) -> dict:
    ids = [int(i) for i in ids]
    if len(ids) < 2:
        return {"blad": "Zaznacz co najmniej dwie osoby."}
    db = galeria._db()
    try:
        przygotuj(db)
        # zostaje osoba z imieniem (albo pierwsza)
        cel = next((i for i in ids if (db.execute("SELECT nazwa FROM g_osoby WHERE id=?", (i,)).fetchone() or [""])[0]),
                   ids[0])
        for i in ids:
            if i != cel:
                db.execute("UPDATE g_twarze SET osoba=? WHERE osoba=?", (cel, i))
                db.execute("DELETE FROM g_osoby WHERE id=?", (i,))
        db.commit()
    finally:
        db.close()
    return {"ok": True, "osoba": cel}


def ukryj(galeria, osoba: int, tak: bool = True) -> dict:
    db = galeria._db()
    try:
        przygotuj(db)
        db.execute("UPDATE g_osoby SET ukryta=? WHERE id=?", (1 if tak else 0, int(osoba)))
        db.commit()
    finally:
        db.close()
    return {"ok": True}


def odlacz(galeria, twarz: int) -> dict:
    """„To nie ta osoba” — twarz zostaje bez osoby i grupowanie już jej nie przypisze."""
    db = galeria._db()
    try:
        przygotuj(db)
        db.execute("UPDATE g_twarze SET osoba=NULL, reczna=1 WHERE id=?", (int(twarz),))
        db.commit()
    finally:
        db.close()
    return {"ok": True}


def przypisz(galeria, twarz: int, osoba: int) -> dict:
    db = galeria._db()
    try:
        przygotuj(db)
        db.execute("UPDATE g_twarze SET osoba=?, reczna=1 WHERE id=?", (int(osoba), int(twarz)))
        db.commit()
    finally:
        db.close()
    return {"ok": True}


def osoba_w_tekscie(db, slowo: str) -> int | None:
    """Imię z wyszukiwarki → id osoby (pełne imię albo początek, min. 3 litery)."""
    s = slowo.strip().lower()
    if len(s) < 3:
        return None
    try:
        r = db.execute("SELECT id FROM g_osoby WHERE nazwa != '' AND (lower(nazwa) = ? OR lower(nazwa) LIKE ?) "
                       "ORDER BY lower(nazwa) = ? DESC LIMIT 1", (s, s + "%", s)).fetchone()
    except Exception:  # noqa: BLE001 — baza bez tabel osób
        return None
    return r[0] if r else None


def otworz_baze(baza):  # dla testów / narzędzi
    db = skaner.otworz_baze(baza)
    przygotuj(db)
    return db
