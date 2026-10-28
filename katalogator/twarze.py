"""👤 Osoby: wykrywanie twarzy na zdjęciach i grupowanie ich w osoby — w całości na komputerze, bez chmury.

Dwa silniki do wyboru (⚙ Ustawienia):
• standardowy — wykrywanie YuNet (OpenCV, model 230 KB w programie), rozpoznawanie SFace (38 MB, pobierany raz
  z oficjalnego repozytorium OpenCV);
• dokładniejszy — InsightFace buffalo_l (jak w Immich): wykrywanie SCRFD-10G, rozpoznawanie ArcFace ResNet50
  (ok. 190 MB, pobierany raz z wydania InsightFace na GitHubie). Lepiej znajduje małe i odwrócone twarze i pewniej
  odróżnia osoby. Licencja modeli InsightFace: tylko użytek niekomercyjny (prywatne zdjęcia — tak).
Zmiana silnika: zdjęcia są przeglądane ponownie (w tle, można przerwać), a nowa twarz przejmuje osobę (imię)
od starej twarzy w tym samym miejscu zdjęcia — imiona i połączenia zostają. Dla każdej twarzy zapisujemy wektor cech
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
import zipfile
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

URL_BUFFALO = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"
PLIKI_BUFFALO = {"det_10g.onnx": "5838f7fe053675b1c7a08b633df49e7af5495cee0493c7dcf6697200b85b5b91",
                 "w600k_r50.onnx": "4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43"}
# dim — długość wektora cech (po niej poznajemy, którym silnikiem policzono twarz); podobne — próg jak PODOBNE
# (ArcFace: jak w Immich, ostrożnie — rozdzieloną osobę łatwo połączyć, złączone różne osoby trudniej rozplątać)
SILNIKI = {"sface": {"nazwa": "Standardowy (OpenCV YuNet + SFace)", "mb": 38, "dim": 128, "podobne": PODOBNE},
           "arcface": {"nazwa": "Dokładniejszy (InsightFace buffalo_l: SCRFD + ArcFace)", "mb": 190, "dim": 512,
                       "podobne": 0.5}}
SILNIK = "sface"    # wybrany w ustawieniach programu — ustawia aplikacja
PEWNOSC_SCRFD = 0.6
_WZORZEC_ARCFACE = [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]]

SCHEMAT = """
CREATE TABLE IF NOT EXISTS g_twarze_pliki (sciezka TEXT PRIMARY KEY, mtime REAL NOT NULL, n INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS g_osoby (id INTEGER PRIMARY KEY AUTOINCREMENT, nazwa TEXT NOT NULL DEFAULT '',
                                    ukryta INTEGER NOT NULL DEFAULT 0, okladka INTEGER);
CREATE TABLE IF NOT EXISTS g_twarze (id INTEGER PRIMARY KEY AUTOINCREMENT, sciezka TEXT NOT NULL,
                                     x REAL, y REAL, w REAL, h REAL, wynik REAL, wektor BLOB NOT NULL,
                                     osoba INTEGER, reczna INTEGER NOT NULL DEFAULT 0, miniatura BLOB);
CREATE INDEX IF NOT EXISTS g_twarze_sciezka ON g_twarze(sciezka);
CREATE INDEX IF NOT EXISTS g_twarze_osoba ON g_twarze(osoba);
CREATE TABLE IF NOT EXISTS g_twarze_meta (klucz TEXT PRIMARY KEY, wartosc TEXT);
"""

_STANY: dict[str, dict] = {}   # baza → stan zadania (jedno wykrywanie na bazę naraz)
_BLOKADA = threading.Lock()


def dostepne() -> str | None:
    """None, gdy można wykrywać; inaczej powód (brak OpenCV / ONNX Runtime)."""
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        if SILNIK == "arcface":
            import onnxruntime  # noqa: F401
    except ImportError:
        return "Brak modułu OpenCV / ONNX Runtime — zainstaluj nową wersję Katalogatora."
    return None


def _katalog_modeli() -> Path:
    return Path(KATALOG_MODELI or Path.home() / ".katalogator" / "modele")


def model_pobrany(silnik: str | None = None) -> bool:
    if (silnik or SILNIK) == "arcface":
        return all((_katalog_modeli() / "buffalo_l" / n).is_file() for n in PLIKI_BUFFALO)
    return _plik_modelu().is_file()


def _sha(sciezka: Path) -> str:
    h = hashlib.sha256()
    with open(sciezka, "rb") as f:
        for k in iter(lambda: f.read(1 << 20), b""):
            h.update(k)
    return h.hexdigest()


def pobierz_buffalo(postep=lambda *_: None) -> Path:
    """Modele InsightFace buffalo_l — raz, z oficjalnego wydania na GitHubie (paczka 275 MB, zostają 2 pliki
    ok. 190 MB); sprawdzamy sumy SHA-256 rozpakowanych plików."""
    kat = _katalog_modeli() / "buffalo_l"
    if model_pobrany("arcface"):
        return kat
    kat.mkdir(parents=True, exist_ok=True)
    paczka = kat / "buffalo_l.zip.pobieranie"
    try:
        with urllib.request.urlopen(URL_BUFFALO, timeout=60) as r, open(paczka, "wb") as f:
            razem, n = int(r.headers.get("Content-Length") or 0), 0
            while True:
                k = r.read(1 << 20)
                if not k:
                    break
                f.write(k); n += len(k)
                postep(n, razem)
        with zipfile.ZipFile(paczka) as z:
            for nazwa, sha in PLIKI_BUFFALO.items():
                cel = kat / nazwa
                tmp = cel.with_suffix(".tmp")
                with z.open(nazwa) as zr, open(tmp, "wb") as f:
                    for k in iter(lambda: zr.read(1 << 20), b""):
                        f.write(k)
                if _sha(tmp) != sha:
                    tmp.unlink(missing_ok=True)
                    raise OSError(f"pobrany model {nazwa} ma złą sumę kontrolną")
                os.replace(tmp, cel)
    except zipfile.BadZipFile as e:
        raise OSError(f"uszkodzona paczka modeli ({e})") from e
    finally:
        paczka.unlink(missing_ok=True)
    return kat


def przygotuj(db) -> None:
    db.executescript(SCHEMAT)


def _plik_modelu() -> Path:
    return _katalog_modeli() / MODEL_ROZPOZNAWANIA


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


class _SilnikArcFace:
    """InsightFace buffalo_l przez ONNX Runtime: SCRFD (twarze + 5 punktów) → wyrównanie do 112×112 → ArcFace."""
    WEJSCIE = 640

    def __init__(self, kat: Path):
        import cv2
        import onnxruntime as ort
        self.cv2 = cv2
        opcje = ort.SessionOptions()
        opcje.log_severity_level = 3
        self.det = ort.InferenceSession(str(kat / "det_10g.onnx"), opcje, providers=["CPUExecutionProvider"])
        self.rec = ort.InferenceSession(str(kat / "w600k_r50.onnx"), opcje, providers=["CPUExecutionProvider"])
        self._kotwice: dict = {}

    def _wykryj(self, bgr):
        import numpy as np
        cv2, rozm = self.cv2, self.WEJSCIE
        h, w = bgr.shape[:2]
        skala = rozm / max(h, w)
        mala = cv2.resize(bgr, (max(1, int(w * skala)), max(1, int(h * skala))))
        plotno = np.zeros((rozm, rozm, 3), np.uint8)
        plotno[:mala.shape[0], :mala.shape[1]] = mala
        blob = cv2.dnn.blobFromImage(plotno, 1.0 / 128, (rozm, rozm), (127.5, 127.5, 127.5), swapRB=True)
        wy = self.det.run(None, {self.det.get_inputs()[0].name: blob})
        ramki, wyniki, punkty = [], [], []
        for i, krok in enumerate((8, 16, 32)):
            s, b, k = wy[i][:, 0], wy[i + 3] * krok, wy[i + 6] * krok
            klucz = (rozm // krok, krok)
            if klucz not in self._kotwice:
                n = rozm // krok
                srodki = (np.stack(np.mgrid[:n, :n][::-1], axis=-1).astype(np.float32) * krok).reshape(-1, 2)
                self._kotwice[klucz] = np.repeat(srodki, 2, axis=0)  # 2 kotwice na punkt siatki
            c = self._kotwice[klucz]
            ok = np.where(s >= PEWNOSC_SCRFD)[0]
            ramki.append(np.hstack([c[ok] - b[ok, :2], c[ok] + b[ok, 2:]]))
            punkty.append(np.stack([c[ok, 0:1] + k[ok, 0::2], c[ok, 1:2] + k[ok, 1::2]], axis=-1))
            wyniki.append(s[ok])
        ramki, wyniki, punkty = np.vstack(ramki) / skala, np.concatenate(wyniki), np.vstack(punkty) / skala
        zostaw = cv2.dnn.NMSBoxes([[float(x1), float(y1), float(x2 - x1), float(y2 - y1)] for x1, y1, x2, y2 in ramki],
                                  [float(v) for v in wyniki], PEWNOSC_SCRFD, 0.4)
        zostaw = np.array(zostaw).flatten() if len(zostaw) else []
        return [(ramki[j], float(wyniki[j]), punkty[j]) for j in zostaw]

    def _cecha(self, bgr, pkt):
        import numpy as np
        cv2 = self.cv2
        m, _ = cv2.estimateAffinePartial2D(pkt.astype(np.float32), np.array(_WZORZEC_ARCFACE, np.float32),
                                           method=cv2.LMEDS)
        twarz = cv2.warpAffine(bgr, m, (112, 112), borderValue=0.0)
        blob = cv2.dnn.blobFromImage(twarz, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
        v = self.rec.run(None, {self.rec.get_inputs()[0].name: blob})[0].flatten().astype(np.float32)
        return v / (np.linalg.norm(v) or 1.0)

    def twarze(self, sciezka: str) -> list[dict]:
        bgr, rgb = _obraz(sciezka)
        h, w = bgr.shape[:2]
        out = []
        for (x1, y1, x2, y2), wynik, pkt in self._wykryj(bgr):
            x, y, fw, fh = max(0.0, float(x1)), max(0.0, float(y1)), float(x2 - x1), float(y2 - y1)
            if min(fw, fh) < MIN_TWARZ:
                continue
            m = max(fw, fh) * 0.25
            wyc = rgb.crop((max(0, int(x - m)), max(0, int(y - m)), min(w, int(x + fw + m)), min(h, int(y + fh + m))))
            wyc.thumbnail((160, 160))
            buf = io.BytesIO(); wyc.save(buf, "JPEG", quality=85)
            out.append({"x": x / w, "y": y / h, "w": fw / w, "h": fh / h, "wynik": wynik,
                        "wektor": self._cecha(bgr, pkt).tobytes(), "miniatura": buf.getvalue()})
        return out


def _iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    wsp = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    suma = a[2] * a[3] + b[2] * b[3] - wsp
    return wsp / suma if suma > 0 else 0.0


def _zapisz_twarze(db, sc: str, lista: list[dict], dim: int) -> None:
    """Nowe twarze pliku. Stare twarze z innego silnika (zmiana silnika) — ich osobę (imię) i ręczne decyzje
    przejmuje nowa twarz w tym samym miejscu zdjęcia, potem znikają. Ręczne przypisania z tego samego silnika
    zostają, jak dotąd."""
    stare = db.execute("SELECT id, x, y, w, h, osoba, reczna, length(wektor) dl FROM g_twarze WHERE sciezka=?",
                       (sc,)).fetchall()
    inne = [r for r in stare if r["dl"] != dim * 4]
    db.execute("DELETE FROM g_twarze WHERE sciezka=? AND reczna=0 AND length(wektor)=?", (sc, dim * 4))
    uzyte = set()
    for t in lista:
        osoba, reczna, stara = None, 0, None
        if inne:
            naj = max(inne, key=lambda r: _iou((t["x"], t["y"], t["w"], t["h"]), (r["x"], r["y"], r["w"], r["h"])))
            if naj["id"] not in uzyte and _iou((t["x"], t["y"], t["w"], t["h"]), (naj["x"], naj["y"], naj["w"], naj["h"])) >= 0.3:
                uzyte.add(naj["id"]); osoba, reczna, stara = naj["osoba"], naj["reczna"], naj["id"]
        nowa = db.execute("INSERT INTO g_twarze (sciezka, x, y, w, h, wynik, wektor, miniatura, osoba, reczna) "
                          "VALUES (?,?,?,?,?,?,?,?,?,?)", (sc, t["x"], t["y"], t["w"], t["h"], t["wynik"], t["wektor"],
                                                           t["miniatura"], osoba, reczna)).lastrowid
        if stara is not None:
            db.execute("UPDATE g_osoby SET okladka=? WHERE okladka=?", (nowa, stara))
    if inne:
        db.execute(f"DELETE FROM g_twarze WHERE id IN ({','.join('?' * len(inne))})", [r["id"] for r in inne])


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
    wybrany = SILNIK if SILNIK in SILNIKI else "sface"
    dim = SILNIKI[wybrany]["dim"]
    try:
        komunikat = (lambda n, r: _ustaw(k, komunikat=f"Pobieram model rozpoznawania twarzy (raz): "
                                                     f"{n // 1048576} z {max(1, r // 1048576)} MB"))
        try:
            model = pobierz_buffalo(komunikat) if wybrany == "arcface" else pobierz_model(komunikat)
        except OSError as e:
            _ustaw(k, trwa=False, blad=f"Nie udało się pobrać modelu rozpoznawania twarzy ({e}). "
                                       "Sprawdź internet i spróbuj ponownie — potrzebny tylko raz.")
            return
        silnik = _SilnikArcFace(model) if wybrany == "arcface" else _Silnik(model)
        db = galeria._db()
        try:
            przygotuj(db)
            poprzedni = (db.execute("SELECT wartosc FROM g_twarze_meta WHERE klucz='silnik'").fetchone() or ["sface"])[0]
            if poprzedni != wybrany:  # zmiana silnika: wszystkie zdjęcia od nowa (imiona przechodzą na nowe twarze)
                db.execute("DELETE FROM g_twarze_pliki")
                db.execute("INSERT OR REPLACE INTO g_twarze_meta VALUES ('silnik', ?)", (wybrany,))
                db.commit()
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
                _zapisz_twarze(db, sc, lista, dim)
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
    sil = SILNIKI.get(SILNIK, SILNIKI["sface"])
    dim, prog = sil["dim"], sil["podobne"]
    # tylko wektory bieżącego silnika (w trakcie zmiany silnika w bazie są jeszcze twarze starego)
    nowe = db.execute("SELECT id, wektor FROM g_twarze WHERE osoba IS NULL AND reczna=0 AND length(wektor)=? ORDER BY id",
                      (dim * 4,)).fetchall()
    if not nowe:
        return 0
    srodki: dict[int, list] = {}  # osoba → [suma wektorów, liczba]
    for o, v in db.execute("SELECT osoba, wektor FROM g_twarze WHERE osoba IS NOT NULL AND length(wektor)=?", (dim * 4,)):
        s = srodki.setdefault(o, [np.zeros(dim, np.float32), 0])
        s[0] += np.frombuffer(v, np.float32); s[1] += 1
    ids = list(srodki)
    macierz = np.array([srodki[o][0] / (np.linalg.norm(srodki[o][0]) or 1) for o in ids], np.float32).reshape(-1, dim)
    for tid, v in nowe:
        wek = np.frombuffer(v, np.float32)
        o = None
        if len(ids):
            pod = macierz @ wek
            j = int(pod.argmax())
            if pod[j] >= prog:
                o = ids[j]
        if o is None:
            o = db.execute("INSERT INTO g_osoby (nazwa) VALUES ('')").lastrowid
            srodki[o] = [np.zeros(dim, np.float32), 0]
            ids.append(o)
            macierz = np.vstack([macierz, np.zeros((1, dim), np.float32)])
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
