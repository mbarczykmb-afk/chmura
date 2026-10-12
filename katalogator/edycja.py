"""✏ Edycja zdjęcia w Przeglądarce: obrót, przycięcie, jasność, kontrast, nasycenie, balans bieli.

Podgląd liczy przeglądarka (canvas, te same wzory co tutaj — galeria.js `edFiltr`), a zapis robi program na pełnej
rozdzielczości. Wynik to zawsze JPEG z EXIF-em oryginału (data, aparat, GPS; orientacja = 1, bo obrót jest już
w pikselach). Domyślnie powstaje kopia „<nazwa> (edytowane).jpg” obok oryginału; „Zastąp oryginał” odkłada oryginał
do kosza programu (Odłożone/Usunięte) — można cofnąć.
"""

from __future__ import annotations

import io
import math
import os
import sqlite3

from PIL import Image, ImageEnhance, ImageOps

try:  # zdjęcia HEIC z iPhone'a (jak w analizie)
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:  # pragma: no cover - opcjonalne
    pass

SUWAKI = ("jasnosc", "kontrast", "nasycenie", "temperatura", "odcien")  # każdy -100…100, 0 = bez zmian


def _liczba(v, lo=-100.0, hi=100.0) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    return max(lo, min(hi, x)) if math.isfinite(x) else 0.0


def normalizuj(op: dict) -> dict:
    """Bezpieczne wartości z przeglądarki."""
    op = op or {}
    wynik = {k: _liczba(op.get(k)) for k in SUWAKI}
    wynik["obrot"] = int(_liczba(op.get("obrot"), 0, 270)) // 90 * 90
    wynik["lustro"] = bool(op.get("lustro"))
    c = op.get("ciecie")
    if isinstance(c, (list, tuple)) and len(c) == 4:
        x0, y0, x1, y1 = (_liczba(v, 0, 1) for v in c)
        if x1 - x0 >= 0.01 and y1 - y0 >= 0.01:
            wynik["ciecie"] = [x0, y0, x1, y1]
    return wynik


def zmienia(op: dict) -> bool:
    return bool(op.get("obrot") or op.get("lustro") or op.get("ciecie") or any(op.get(k) for k in SUWAKI))


def lut(op: dict) -> list[int]:
    """Krzywe R, G, B (balans bieli → jasność jako gamma → kontrast) — 768 wartości dla Image.point."""
    t, n = op.get("temperatura", 0) / 100, op.get("odcien", 0) / 100
    wzm = (1 + 0.25 * t, 1 - 0.2 * n, 1 - 0.25 * t)  # cieplej: więcej czerwieni, mniej niebieskiego; odcień: zieleń
    gamma = 2 ** (-op.get("jasnosc", 0) / 100)       # +100 = wyraźnie jaśniej, bez przepalania świateł
    k = 1 + op.get("kontrast", 0) / 100
    wynik = []
    for w in wzm:
        for i in range(256):
            v = min(255.0, i * w)
            v = 255 * (v / 255) ** gamma
            v = (v - 128) * k + 128
            wynik.append(max(0, min(255, round(v))))
    return wynik


def zastosuj(im: Image.Image, op: dict) -> Image.Image:
    im = ImageOps.exif_transpose(im).convert("RGB")
    if op.get("obrot"):
        im = im.rotate(-op["obrot"], expand=True)  # zgodnie z ruchem wskazówek zegara
    if op.get("lustro"):
        im = ImageOps.mirror(im)
    if op.get("ciecie"):
        x0, y0, x1, y1 = op["ciecie"]
        w, h = im.size
        im = im.crop((round(x0 * w), round(y0 * h), max(round(x0 * w) + 1, round(x1 * w)),
                      max(round(y0 * h) + 1, round(y1 * h))))
    if any(op.get(k) for k in ("jasnosc", "kontrast", "temperatura", "odcien")):
        im = im.point(lut(op))
    if op.get("nasycenie"):
        im = ImageEnhance.Color(im).enhance(1 + op["nasycenie"] / 100)  # szarość (299/587/114) + różnica × s
    return im


def _exif(oryginal: Image.Image) -> bytes | None:
    try:
        ex = oryginal.getexif()
        if not ex:
            return None
        ex[0x0112] = 1  # orientacja: piksele są już obrócone
        for tag in (0x0201, 0x0202):  # stara miniatura w IFD1 nie pasowałaby do zdjęcia
            ex.pop(tag, None)
        return ex.tobytes()
    except Exception:
        return None


def wykonaj(sciezka: str, op: dict, jakosc: int = 92) -> bytes:
    """Edytowane zdjęcie jako JPEG (pełna rozdzielczość, EXIF oryginału)."""
    with Image.open(sciezka) as org:
        im = zastosuj(org, op)  # najpierw obrót wg EXIF-u — dopiero potem orientacja = 1 w kopii EXIF-u
        exif, icc = _exif(org), org.info.get("icc_profile")
    buf = io.BytesIO()
    dod = {"exif": exif} if exif else {}
    if icc:
        dod["icc_profile"] = icc
    im.save(buf, "JPEG", quality=jakosc, subsampling=0 if jakosc >= 90 else 2, optimize=True, **dod)
    return buf.getvalue()


def wolna_nazwa(folder: str, rdzen: str, rozszerzenie: str = ".jpg") -> str:
    for i in range(1, 1000):
        p = os.path.join(folder, f"{rdzen}{'' if i == 1 else f' {i}'}{rozszerzenie}")
        if not os.path.exists(p):
            return p
    raise OSError("za dużo kopii o tej nazwie")


def zapisz(db: sqlite3.Connection, wiersz, op: dict, zastap: bool = False) -> dict:
    """Zapisuje edycję: kopia obok (domyślnie) albo w miejsce oryginału (oryginał → kosz programu, z cofaniem)."""
    from . import skaner, usuwanie
    op = normalizuj(op)
    if not zmienia(op):
        return {"blad": "Nic nie zmieniono."}
    sc = wiersz["sciezka"]
    try:
        dane = wykonaj(sc, op)
    except Exception as e:  # uszkodzony plik / format, którego nie umiemy otworzyć
        return {"blad": f"Nie udało się otworzyć zdjęcia: {type(e).__name__}: {e}"}
    folder, nazwa = os.path.split(sc)
    rdzen, rozsz = os.path.splitext(nazwa)
    partia = None
    if zastap:
        u = usuwanie.usun(db, [wiersz["rowid"] if "rowid" in wiersz.keys() else wiersz["id"]])
        if not u.get("usuniete"):
            return {"blad": "Nie udało się odłożyć oryginału: " + "; ".join(u.get("pominiete") or ["?"])}
        partia = u["partia"]
        cel = sc if rozsz.lower() in (".jpg", ".jpeg") and not os.path.exists(sc) else wolna_nazwa(folder, rdzen)
    else:
        cel = wolna_nazwa(folder, f"{rdzen} (edytowane)")
    try:
        with open(cel, "xb") as f:
            f.write(dane)
    except OSError as e:
        if partia:
            usuwanie.cofnij(db, partia)
        return {"blad": f"Nie udało się zapisać: {e.strerror or e}"}
    nowy = skaner.dodaj_plik(db, cel, wiersz["korzen"])
    _przenies_metadane(db, wiersz, cel, nowy)
    return {"ok": True, "id": nowy, "sciezka": cel, "nazwa": os.path.basename(cel), "partia": partia,
            "zastapiono": bool(zastap)}


def _przenies_metadane(db: sqlite3.Connection, wiersz, cel: str, nowy: int) -> None:
    """Data i miejsce ustawione ręcznie (.xmp obok HEIC/PNG) albo z nazwy pliku — także w EXIF-ie wersji edytowanej."""
    from datetime import datetime

    from . import lokalizacja, skaner
    r = db.execute("SELECT data, lat FROM pliki WHERE rowid=?", (nowy,)).fetchone()
    zmiana = False
    try:
        if wiersz["data"] and wiersz["zrodlo_daty"] != "plik" and (not r["data"] or r["data"] != wiersz["data"]):
            lokalizacja.zapisz_date_w_pliku(cel, datetime.fromisoformat(wiersz["data"]))
            zmiana = True
        if wiersz["lat"] is not None and r["lat"] is None:
            lokalizacja.zapisz_w_pliku(cel, wiersz["lat"], wiersz["lon"])
            zmiana = True
    except Exception:
        return  # zdjęcie zapisane — brak daty w EXIF-ie nie jest powodem do błędu
    if zmiana:
        skaner.dodaj_plik(db, cel, wiersz["korzen"])


def cofnij(db: sqlite3.Connection, id_: int, partia: int | None) -> dict:
    """Cofnięcie „Zastąp oryginał”: usuwa wersję edytowaną i przywraca oryginał z kosza programu."""
    from . import usuwanie
    r = db.execute("SELECT sciezka FROM pliki WHERE rowid=?", (int(id_),)).fetchone()
    if r:
        try:
            os.remove(r[0])
        except FileNotFoundError:
            pass
        except OSError as e:
            return {"blad": f"Nie udało się usunąć wersji edytowanej: {e.strerror or e}"}
        db.execute("DELETE FROM pliki WHERE rowid=?", (int(id_),))
        db.commit()
    if partia:
        return usuwanie.cofnij(db, int(partia))
    return {"przywrocone": 0, "bledy": []}
