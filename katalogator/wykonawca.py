"""Wykonanie planu: kopiowanie / przenoszenie z weryfikacją, dziennikiem i cofaniem.

Zasady bezpieczeństwa:
- kopia powstaje najpierw jako plik tymczasowy, potem jest sprawdzana sumą kontrolną
  i dopiero wtedy dostaje docelową nazwę;
- przy przenoszeniu oryginał znika dopiero po udanej weryfikacji kopii
  (na tym samym dysku — szybka zmiana nazwy bez kopiowania);
- nic nie jest nadpisywane: zajęta nazwa dostaje dopisek „ (2)”;
- każda operacja trafia do dziennika i można ją cofnąć.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time

from . import planista, typy
from .skaner import Przerwano

SCHEMAT = """
CREATE TABLE IF NOT EXISTS wykonanie (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    partia   INTEGER NOT NULL,
    plan_id  INTEGER NOT NULL,
    zrodlo   TEXT NOT NULL,
    cel      TEXT NOT NULL,
    tryb     TEXT NOT NULL,
    usuniete INTEGER NOT NULL DEFAULT 0,
    rozmiar  INTEGER NOT NULL,
    mtime    REAL NOT NULL,
    czas     REAL NOT NULL,
    cofniete INTEGER NOT NULL DEFAULT 0
);
-- przerwane kopie dużych plików czekające na wznowienie (sprzątane, gdy plan już ich nie potrzebuje)
CREATE TABLE IF NOT EXISTS niedokonczone (tmp TEXT PRIMARY KEY);
"""
BLOK = 4 << 20
TMP = ".katalogator-tmp"
STAN = ".json"  # obok pliku tymczasowego: skąd kopia i sumy gotowych kawałków (do wznowienia)
KAWALEK = 64 << 20  # jednostka wznawiania i sprawdzania kopii (wielokrotność BLOK)
WZNAWIANIE_OD = 256 << 20  # od tej wielkości przerwana kopia jest wznawiana, a nie zaczynana od zera
ZAPIS_STANU_CO = 20.0  # s


def przygotuj(db: sqlite3.Connection) -> None:
    planista.przygotuj(db)
    db.executescript(SCHEMAT)


def _wolumin(sciezka: str) -> str:
    d, _ = os.path.splitdrive(os.path.abspath(sciezka))
    if d:
        return d.lower()
    try:
        return str(os.stat(sciezka).st_dev)
    except OSError:
        return ""


def ten_sam_wolumin(a: str, b_folder: str) -> bool:
    b = b_folder
    while b and not os.path.exists(b):
        nb = os.path.dirname(b)
        if nb == b:
            break
        b = nb
    wa, wb = _wolumin(a), _wolumin(b)
    return bool(wa) and wa == wb


def _hash(sciezka: str, przerwij=None, licz=None) -> str:
    h = hashlib.blake2b(digest_size=20)
    with open(sciezka, "rb") as f:
        while True:
            if przerwij is not None and przerwij.is_set():
                raise Przerwano(sciezka)
            k = f.read(BLOK)
            if not k:
                return h.hexdigest()
            h.update(k)
            if licz:
                licz(len(k))


def kopiuj_z_weryfikacja(zrodlo: str, cel: str, przerwij=None, licz=None) -> None:
    """Kopiuje do pliku tymczasowego, liczy sumy kawałków w locie, weryfikuje kopię i nadaje nazwę.

    Duży plik (od WZNAWIANIE_OD) po przerwie — zerwana sieć, „Przerwij”, zamknięty program — jest kopiowany
    dalej od ostatniego zapisanego kawałka, a nie od zera. Sumy kawałków pochodzą ze źródła, więc końcowe
    sprawdzenie obejmuje także część skopiowaną przed przerwą.
    """
    tmp = cel + TMP
    st = os.stat(zrodlo)
    duzy = st.st_size >= WZNAWIANIE_OD
    sumy = _wczytaj_stan(tmp, zrodlo, st) if duzy else []
    zachowaj = duzy  # po przerwie duży plik tymczasowy zostaje do wznowienia
    try:
        start = len(sumy) * KAWALEK
        with open(zrodlo, "rb") as fz, open(tmp, "r+b" if start else "wb") as fc:
            fz.seek(start)
            fc.seek(start)
            fc.truncate(start)
            if start and licz:
                licz(start)
            h, w_kawalku, zapis = hashlib.blake2b(digest_size=20), 0, time.monotonic()
            try:
                while True:
                    if przerwij is not None and przerwij.is_set():
                        raise Przerwano(zrodlo)
                    k = fz.read(min(BLOK, KAWALEK - w_kawalku))  # kawałki zawsze równe (wznawianie od granicy)
                    if k:
                        h.update(k)
                        fc.write(k)
                        w_kawalku += len(k)
                        if licz:
                            licz(len(k))
                    if w_kawalku >= KAWALEK or (not k and w_kawalku):
                        sumy.append(h.hexdigest())
                        h, w_kawalku = hashlib.blake2b(digest_size=20), 0
                        if duzy and time.monotonic() - zapis > ZAPIS_STANU_CO:
                            _zapisz_stan(fc, tmp, zrodlo, st, sumy)
                            zapis = time.monotonic()
                    if not k:
                        break
                fc.flush()
                os.fsync(fc.fileno())
            except BaseException:
                if duzy:
                    try:  # zapisane dotąd kawałki — tylko gdy na pewno są na dysku
                        _zapisz_stan(fc, tmp, zrodlo, st, sumy)
                    except OSError:
                        pass
                raise
        if _sumy_kawalkow(tmp, przerwij, licz) != sumy:
            zachowaj = False
            raise OSError("kopia różni się od oryginału (błąd zapisu lub sieci)")
        shutil.copystat(zrodlo, tmp)
        if os.path.exists(cel):
            zachowaj = False
            raise FileExistsError(cel)
        os.replace(tmp, cel)
        zachowaj = False
    finally:
        if not zachowaj:
            for sm in (tmp, tmp + STAN):
                if os.path.exists(sm):
                    try:
                        os.remove(sm)
                    except OSError:
                        pass


def _sumy_kawalkow(sciezka: str, przerwij=None, licz=None) -> list[str]:
    sumy = []
    with open(sciezka, "rb") as f:
        while True:
            h, n = hashlib.blake2b(digest_size=20), 0
            while n < KAWALEK:
                if przerwij is not None and przerwij.is_set():
                    raise Przerwano(sciezka)
                k = f.read(min(BLOK, KAWALEK - n))
                if not k:
                    break
                h.update(k)
                n += len(k)
                if licz:
                    licz(len(k))
            if not n:
                return sumy
            sumy.append(h.hexdigest())


def _zapisz_stan(fc, tmp: str, zrodlo: str, st, sumy: list[str]) -> None:
    """Punkt wznowienia: najpierw dane na dysk, potem opis (zapis atomowy)."""
    fc.flush()
    os.fsync(fc.fileno())
    dane = {"zrodlo": os.path.abspath(zrodlo), "rozmiar": st.st_size, "mtime": st.st_mtime,
            "kawalek": KAWALEK, "sumy": sumy}
    with open(tmp + STAN + ".nowy", "w", encoding="utf-8") as f:
        json.dump(dane, f)
    os.replace(tmp + STAN + ".nowy", tmp + STAN)


def _wczytaj_stan(tmp: str, zrodlo: str, st) -> list[str]:
    """Sumy kawałków już skopiowanych do tmp — albo [], gdy nie ma czego wznawiać (lub to inny plik)."""
    try:
        with open(tmp + STAN, encoding="utf-8") as f:
            d = json.load(f)
        sumy = d["sumy"]
        if (d["zrodlo"] == os.path.abspath(zrodlo) and d["rozmiar"] == st.st_size and d["mtime"] == st.st_mtime
                and d["kawalek"] == KAWALEK and isinstance(sumy, list)
                and os.path.getsize(tmp) >= len(sumy) * KAWALEK and len(sumy) * KAWALEK <= st.st_size):
            return [str(x) for x in sumy]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return []


def _wolna(cel: str) -> str:
    if not os.path.exists(cel):
        return cel
    baza, ext = os.path.splitext(cel)
    i = 2
    while os.path.exists(f"{baza} ({i}){ext}"):
        i += 1
    return f"{baza} ({i}){ext}"


def do_zrobienia(db: sqlite3.Connection, oryginaly: bool = True, folder: str | None = None) -> list[sqlite3.Row]:
    """Pliki do skopiowania/przeniesienia; oryginaly=True — także „przenieś” plików, które już są w miejscu
    docelowym (np. po wcześniejszym kopiowaniu): oryginał znika po sprawdzeniu, że kopia jest identyczna.
    folder: tylko ten folder drzewa (z podfolderami) — próba przed porządkowaniem całości."""
    przygotuj(db)
    gdzie, arg = "", []
    if folder:
        f = folder.strip("/")
        gdzie, arg = " AND cel LIKE ? ESCAPE '\\'", [planista._like(f + "/") + "%"]
    return db.execute(
        "SELECT * FROM plan WHERE tryb IN ('kopiuj','przenies') AND (wynik IS NULL OR wynik LIKE 'blad%') AND "
        "((pominiety=0 AND stan='nowy') OR (? AND stan='juz_jest' AND tryb='przenies' AND jest IS NOT NULL))"
        + gdzie + " ORDER BY id", (int(oryginaly), *arg)).fetchall()


def sprawdz(db: sqlite3.Connection, oryginaly: bool = True, folder: str | None = None) -> dict:
    """Ile trzeba skopiować i czy starczy miejsca."""
    wiersze = do_zrobienia(db, oryginaly, folder)
    cel = planista.meta(db).get("cel", "")
    potrzeba = sum(w["rozmiar"] for w in wiersze if w["stan"] == "nowy"
                   and (w["tryb"] == "kopiuj" or not ten_sam_wolumin(w["sciezka"], cel)))
    try:
        os.makedirs(cel, exist_ok=True)
        wolne = shutil.disk_usage(cel).free
    except OSError as e:
        return {"blad": f"Brak dostępu do miejsca docelowego: {e.strerror or e}", "plikow": len(wiersze)}
    wynik = {"plikow": len(wiersze), "bajtow": sum(w["rozmiar"] for w in wiersze), "potrzeba": potrzeba,
             "wolne": wolne, "starczy": wolne > potrzeba * 1.02 + 50_000_000, "cel": cel,
             "najwiekszy": max((w["rozmiar"] for w in wiersze), default=0),
             "oryginaly": sum(1 for w in wiersze if w["stan"] == "juz_jest"),
             "oryginaly_b": sum(w["rozmiar"] for w in wiersze if w["stan"] == "juz_jest")}
    if system_plikow(cel) in FAT:
        wynik["za_duze_fat"] = sum(1 for w in wiersze if w["rozmiar"] > MAKS_FAT32 and w["stan"] == "nowy")
    return wynik


FAT = {"fat", "fat12", "fat16", "fat32", "vfat", "msdos"}
MAKS_FAT32 = (4 << 30) - 1  # FAT32 nie zapisze pliku większego niż 4 GB bez 1 bajta


def system_plikow(sciezka: str) -> str:
    """Nazwa systemu plików (małymi literami: ntfs, exfat, fat32, vfat, ext4…) albo "" gdy nieznany."""
    try:
        sciezka = os.path.abspath(sciezka)
        if os.name == "nt":
            import ctypes
            korzen = ctypes.create_unicode_buffer(1024)
            nazwa = ctypes.create_unicode_buffer(64)
            k32 = ctypes.windll.kernel32
            if not k32.GetVolumePathNameW(sciezka, korzen, 1024):
                return ""
            if not k32.GetVolumeInformationW(korzen, None, 0, None, None, None, nazwa, 64):
                return ""
            return nazwa.value.lower()
        najlepszy, typ = "", ""
        with open("/proc/mounts", encoding="utf-8") as f:
            for linia in f:
                cz = linia.split()
                if len(cz) >= 3:
                    punkt = cz[1].replace("\\040", " ")
                    if (sciezka == punkt or sciezka.startswith(punkt.rstrip("/") + "/")) and len(punkt) >= len(najlepszy):
                        najlepszy, typ = punkt, cz[2].lower()
        return typ
    except (OSError, AttributeError, ValueError):
        return ""


def wykonaj(db: sqlite3.Connection, postep=None, przerwij=None, usun_puste: bool = True,
            usun_oryginaly: bool = True, folder: str | None = None) -> dict:
    przygotuj(db)
    spr = sprawdz(db, usun_oryginaly, folder)
    if spr.get("blad"):
        raise OSError(spr["blad"])
    if not spr["starczy"]:
        raise OSError(f"Za mało miejsca w miejscu docelowym: potrzeba {spr['potrzeba'] / 1e9:.1f} GB, "
                      f"wolne {spr['wolne'] / 1e9:.1f} GB.")
    cel_root = spr["cel"]
    wiersze = do_zrobienia(db, usun_oryginaly, folder)
    # granice sprzątania pustych folderów: foldery źródłowe sprzed porządkowania (potem ich wpisy znikają z bazy)
    korzenie = [r[0] for r in db.execute("SELECT DISTINCT korzen FROM pliki")]
    partia = int(time.time() * 1000)
    bajty = [0]  # praca: kopia i jej sprawdzenie to dwa odczyty pliku
    razem = spr["bajtow"]
    praca_razem = max(1, spr["bajtow"] + spr["potrzeba"] + spr["oryginaly_b"])  # „już jest”: dwa odczyty

    def jako_bajty(praca: int) -> int:  # pasek i tempo w bajtach plików, ale z czasem sprawdzania kopii
        return min(razem, round(praca * razem / praca_razem))
    ok = bledy = 0
    przeniesione_foldery: set[str] = set()
    from .stabilnosc import Straznik
    straznik = Straznik([r[0] for r in db.execute("SELECT DISTINCT korzen FROM pliki")] + [cel_root], przerwij,
                        getattr(postep, "czeka", None))
    biezacy = {"i": 0, "plik": "", "t": 0.0}

    def zglos(wymus=False):
        teraz = time.monotonic()
        if postep and (wymus or teraz - biezacy["t"] > 0.5):
            biezacy["t"] = teraz
            postep("kopiowanie", biezacy["i"], len(wiersze), jako_bajty(bajty[0]), bajty_razem=razem,
                   plik=biezacy["plik"])

    def licz(n):  # w trakcie kopiowania — pasek rusza się także przy jednym dużym filmie
        bajty[0] += n
        zglos()

    for i, w in enumerate(wiersze, 1):
        if przerwij is not None and przerwij.is_set():
            raise Przerwano(w["sciezka"])
        biezacy.update(i=i - 1, plik=w["sciezka"])
        zglos(wymus=True)
        przed = bajty[0]
        for proba in range(3):
            bajty[0] = przed  # ponowienie po przerwie w sieci liczy plik od nowa
            try:
                _wykonaj_plik(db, w, cel_root, partia, przerwij, licz, przeniesione_foldery)
                ok += 1
                break
            except Przerwano:
                _zapamietaj_tmp(db, cel_root, w)
                db.commit()
                raise
            except OSError as e:
                dst = os.path.join(cel_root, *w["cel"].split("/"))
                if proba < 2 and getattr(e, "winerror", None) in (32, 33):
                    # plik akurat otwarty (Przeglądarka odtwarza film, antywirus, podgląd Eksploratora) — chwila i znowu
                    time.sleep(2 + 3 * proba)
                    continue
                if proba < 2 and straznik.utracono(w["sciezka"], dst):
                    continue  # dysk wrócił — ten sam plik jeszcze raz (kopia ruszy od miejsca przerwania)
                _zapamietaj_tmp(db, cel_root, w)
                db.execute("UPDATE plan SET wynik=? WHERE id=?", (f"blad: {e.strerror or e}"[:300], w["id"]))
                bledy += 1
                break
        db.commit()  # po każdym pliku: kopiowanie następnego może trwać minuty
    _sprzatnij_tmp(db, cel_root)
    db.commit()
    przenies_decyzje(db)
    usuniete_foldery = _usun_puste(przeniesione_foldery, korzenie) if usun_puste else 0
    if postep:
        postep("gotowe", len(wiersze), len(wiersze), jako_bajty(bajty[0]), bajty_razem=razem)
    return {"zrobione": ok, "bledy": bledy, "bajty": jako_bajty(bajty[0]), "partia": partia,
            "usuniete_foldery": usuniete_foldery}


def _wykonaj_plik(db, w, cel_root: str, partia: int, przerwij, licz, przeniesione_foldery: set) -> None:
    """Jeden plik planu: kopia/przeniesienie + wpis w dzienniku. OSError = nie udało się."""
    juz_jest = w["stan"] == "juz_jest"  # przenieś pliku, który już leży w miejscu docelowym: tylko usuń oryginał
    dst = os.path.join(cel_root, *(w["jest"] if juz_jest else w["cel"]).split("/"))
    zrodlowy = db.execute("SELECT * FROM pliki WHERE rowid=?", (w["plik_id"],)).fetchone() \
        if w["plik_id"] is not None else None
    st = os.stat(w["sciezka"])
    if st.st_size != w["rozmiar"]:
        raise OSError("plik zmienił się od skanu — przeskanuj ponownie")
    if not juz_jest and st.st_size > MAKS_FAT32 \
            and (w["tryb"] == "kopiuj" or not ten_sam_wolumin(w["sciezka"], cel_root)) and system_plikow(cel_root) in FAT:
        raise OSError("plik większy niż 4 GB, a dysk docelowy ma system FAT32 — sformatuj go jako exFAT lub NTFS")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tryb_logu = w["tryb"]
    if _ten_sam_plik(w["sciezka"], dst):
        # to już jest ten plik (np. ten sam folder pod dwiema nazwami: Z:\… i \\192.168…\…) — nic nie ruszamy,
        # a zwłaszcza nie usuwamy „oryginału”, który jest jedyną kopią
        db.execute("UPDATE plan SET wynik='ok' WHERE id=?", (w["id"],))
        return
    if os.path.exists(dst) and os.path.getsize(dst) == w["rozmiar"] and \
            _hash(dst, przerwij, licz) == _hash(w["sciezka"], przerwij, licz):
        # identyczny plik już jest w bibliotece — nie tworzymy kopii „ (2)”
        usuniete = 0
        if w["tryb"] == "przenies":
            os.remove(w["sciezka"])
            usuniete = 1
            przeniesione_foldery.add(os.path.dirname(w["sciezka"]))
            if w["plik_id"] is not None:
                db.execute("DELETE FROM pliki WHERE rowid=?", (w["plik_id"],))
        _do_biblioteki(db, zrodlowy, dst, cel_root)
        db.execute("INSERT INTO wykonanie(partia, plan_id, zrodlo, cel, tryb, usuniete, rozmiar, mtime, czas) "
                   "VALUES (?,?,?,?,?,?,?,?,?)",
                   (partia, w["id"], w["sciezka"], dst, "juz_byl", usuniete, w["rozmiar"], st.st_mtime,
                    time.time()))
        db.execute("UPDATE plan SET wynik='ok' WHERE id=?", (w["id"],))
        return
    if juz_jest:  # kopii w bibliotece nie ma albo jest inna — nic nie usuwamy
        raise OSError("kopia w miejscu docelowym zniknęła albo się zmieniła — oryginał zostaje; utwórz propozycję "
                      "ponownie")
    dst = _wolna(dst)
    usuniete = 0
    if w["tryb"] == "przenies" and ten_sam_wolumin(w["sciezka"], os.path.dirname(dst)):
        try:
            os.rename(w["sciezka"], dst)
            usuniete = 1
            licz(w["rozmiar"])
        except OSError:
            usuniete = 0
    if not usuniete:
        kopiuj_z_weryfikacja(w["sciezka"], dst, przerwij, licz)
        if w["tryb"] == "przenies":
            os.remove(w["sciezka"])
            usuniete = 1
    if usuniete:
        przeniesione_foldery.add(os.path.dirname(w["sciezka"]))
        if w["plik_id"] is not None:
            db.execute("DELETE FROM pliki WHERE rowid=?", (w["plik_id"],))
    _do_biblioteki(db, zrodlowy, dst, cel_root)
    db.execute("INSERT INTO wykonanie(partia, plan_id, zrodlo, cel, tryb, usuniete, rozmiar, mtime, czas) "
               "VALUES (?,?,?,?,?,?,?,?,?)",
               (partia, w["id"], w["sciezka"], dst, tryb_logu, usuniete, w["rozmiar"], st.st_mtime, time.time()))
    db.execute("UPDATE plan SET wynik='ok' WHERE id=?", (w["id"],))


def przenies_decyzje(db: sqlite3.Connection) -> int:
    """Twoje decyzje (dokument / zdjęcie / śmieci) i wyniki analizy idą za plikiem do biblioteki. Zapisane są pod
    ścieżką pliku — po uporządkowaniu (nowa ścieżka) „znikały” i te same zdjęcia wracały do przejrzenia.
    Bezpieczne do wołania wiele razy (dopisuje tylko brakujące)."""
    przygotuj(db)
    tabele = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    n = 0
    if "decyzje_dok" in tabele:
        n += db.execute("INSERT OR IGNORE INTO decyzje_dok(sciezka, dokument) SELECT w.cel, d.dokument "
                        "FROM wykonanie w JOIN decyzje_dok d ON d.sciezka = w.zrodlo").rowcount
    if "kategorie" in tabele:
        n += db.execute("INSERT OR IGNORE INTO kategorie(sciezka, kategoria) SELECT w.cel, k.kategoria "
                        "FROM wykonanie w JOIN kategorie k ON k.sciezka = w.zrodlo").rowcount
    if "analiza" in tabele:  # bez ponownego czytania zdjęć z dysku
        kol = [r[1] for r in db.execute("PRAGMA table_info(analiza)") if r[1] not in ("sciezka", "rozmiar", "mtime")]
        db.execute(f"INSERT OR IGNORE INTO analiza(sciezka, rozmiar, mtime, {', '.join(kol)}) "
                   f"SELECT w.cel, p.rozmiar, p.mtime, {', '.join('a.' + k for k in kol)} FROM wykonanie w "
                   f"JOIN analiza a ON a.sciezka = w.zrodlo JOIN pliki p ON p.sciezka = w.cel "
                   f"WHERE p.rozmiar = a.rozmiar")
    db.commit()
    return n


def _tmp_wiersza(cel_root: str, w) -> str:
    return _wolna(os.path.join(cel_root, *w["cel"].split("/"))) + TMP


def _zapamietaj_tmp(db, cel_root: str, w) -> None:
    try:
        tmp = _tmp_wiersza(cel_root, w)
        if os.path.exists(tmp):
            db.execute("INSERT OR IGNORE INTO niedokonczone VALUES (?)", (tmp,))
    except OSError:
        pass


def _sprzatnij_tmp(db, cel_root: str) -> None:
    """Po przejściu całego planu: usuń przerwane kopie, których żaden czekający plik już nie wznowi."""
    zapisane = [r[0] for r in db.execute("SELECT tmp FROM niedokonczone")]
    if not zapisane:
        return
    potrzebne = set()
    for w in db.execute("SELECT cel FROM plan WHERE tryb IN ('kopiuj','przenies') AND pominiety=0 "
                        "AND stan='nowy' AND wynik LIKE 'blad%'"):
        try:
            potrzebne.add(_tmp_wiersza(cel_root, w))
        except OSError:
            pass
    for tmp in zapisane:
        if tmp in potrzebne and os.path.exists(tmp):
            continue
        for sm in (tmp, tmp + STAN):
            try:
                if os.path.exists(sm):
                    os.remove(sm)
            except OSError:
                continue
        db.execute("DELETE FROM niedokonczone WHERE tmp=?", (tmp,))


def _ten_sam_plik(a: str, b: str) -> bool:
    try:
        if os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b)):
            return True
        return os.path.exists(b) and os.path.samefile(a, b)
    except OSError:
        return False


def _do_biblioteki(db, zrodlowy, dst: str, cel_root: str) -> None:
    """Plik w bibliotece od razu trafia do bazy (z datą, GPS i aparatem źródła) — przeglądarka biblioteki
    i kolejne propozycje widzą go bez ponownego skanowania."""
    if zrodlowy is None:
        return
    try:
        st = os.stat(dst)
    except OSError:
        return
    dane = dict(zrodlowy)
    dane.update(sciezka=dst, korzen=os.path.abspath(cel_root), wzgledna=os.path.relpath(dst, cel_root),
                rozmiar=st.st_size, mtime=st.st_mtime, skan=0)
    kol = list(dane)
    db.execute(f"INSERT OR REPLACE INTO pliki({','.join(kol)}) VALUES ({','.join('?' * len(kol))})",
               [dane[k] for k in kol])


# Tylko to wolno usunąć razem z pustym folderem: pliki i foldery tworzone automatycznie przez system i programy.
_SMIECI_DO_USUNIECIA_PLIKI = {"thumbs.db", "desktop.ini", ".ds_store", "ehthumbs.db", ".picasa.ini", ".nomedia"}
_SMIECI_DO_USUNIECIA_FOLDERY = {".wdmc", "@eadir", ".appledouble", ".thumbnails", ".spotlight-v100", ".fseventsd",
                                ".trashes"}


def _smiec(w) -> bool:
    n = w.name.lower()
    if w.is_dir(follow_symlinks=False):
        return n in _SMIECI_DO_USUNIECIA_FOLDERY
    return n in _SMIECI_DO_USUNIECIA_PLIKI or n.startswith("._")


def _usun_puste(foldery: set[str], korzenie: list[str]) -> int:
    """Usuwa foldery źródłowe, które po przeniesieniu zostały puste (lub mają tylko systemowe śmieci).
    Nigdy nie wychodzi poza wybrane foldery i nie usuwa niczego, co nie jest znanym śmieciem (np. folderów
    ukrytych, „Odłożone” czy plików, których nie skanowaliśmy)."""
    granice = [os.path.normcase(os.path.normpath(k)).rstrip("\\/") for k in korzenie if k]

    def wewnatrz(f: str) -> bool:
        nf = os.path.normcase(os.path.normpath(f))
        return any(nf.startswith(g + os.sep) for g in granice)

    usuniete = 0
    for f in sorted(foldery, key=len, reverse=True):
        while f and wewnatrz(f):
            try:
                wpisy = list(os.scandir(f))
            except OSError:
                break
            if not all(_smiec(w) for w in wpisy):
                break
            try:
                for w in wpisy:
                    shutil.rmtree(w.path) if w.is_dir(follow_symlinks=False) else os.remove(w.path)
                os.rmdir(f)
                usuniete += 1
            except OSError:
                break
            nf = os.path.dirname(f)
            if nf == f:
                break
            f = nf
    return usuniete


def ostatnia_partia(db: sqlite3.Connection) -> dict | None:
    przygotuj(db)
    r = db.execute("SELECT partia, COUNT(*) n, SUM(usuniete) przeniesione FROM wykonanie WHERE cofniete=0 "
                   "GROUP BY partia ORDER BY partia DESC LIMIT 1").fetchone()
    return dict(r) if r else None


def cofnij(db: sqlite3.Connection, postep=None, przerwij=None) -> dict:
    """Cofa ostatnie porządkowanie: kopie są usuwane, przeniesione pliki wracają na miejsce."""
    ost = ostatnia_partia(db)
    if not ost:
        return {"cofniete": 0, "bledy": []}
    wiersze = db.execute("SELECT * FROM wykonanie WHERE partia=? AND cofniete=0 ORDER BY id DESC",
                         (ost["partia"],)).fetchall()
    cofniete, bledy = 0, []
    foldery_celu: set[str] = set()
    from .skaner import Zatwierdzanie
    zatwierdz = Zatwierdzanie(db)  # krótkie transakcje — cofanie 50 tys. plików trwa
    for i, w in enumerate(wiersze, 1):
        if przerwij is not None and przerwij.is_set():
            db.commit()
            raise Przerwano(w["cel"])
        if postep and (i % 20 == 1 or i == len(wiersze)):
            postep("cofanie", i - 1, len(wiersze), 0, plik=w["cel"])
        try:
            if not os.path.exists(w["cel"]):
                raise OSError(f"nie ma już pliku {w['cel']}")
            if os.path.getsize(w["cel"]) != w["rozmiar"]:
                raise OSError(f"plik zmieniony po uporządkowaniu: {w['cel']}")
            if w["tryb"] == "juz_byl":
                # plik był w bibliotece wcześniej — zostaje; przywracamy tylko usunięty oryginał
                if w["usuniete"] and not os.path.exists(w["zrodlo"]):
                    os.makedirs(os.path.dirname(w["zrodlo"]), exist_ok=True)
                    kopiuj_z_weryfikacja(w["cel"], w["zrodlo"], przerwij)
            elif w["usuniete"]:
                if os.path.exists(w["zrodlo"]):
                    raise OSError(f"w miejscu oryginału jest już plik: {w['zrodlo']}")
                os.makedirs(os.path.dirname(w["zrodlo"]), exist_ok=True)
                if ten_sam_wolumin(w["cel"], os.path.dirname(w["zrodlo"])):
                    os.rename(w["cel"], w["zrodlo"])
                else:
                    kopiuj_z_weryfikacja(w["cel"], w["zrodlo"], przerwij)
                    os.remove(w["cel"])
            else:
                os.remove(w["cel"])
            if w["tryb"] != "juz_byl":
                foldery_celu.add(os.path.dirname(w["cel"]))
            db.execute("UPDATE wykonanie SET cofniete=1 WHERE id=?", (w["id"],))
            if w["tryb"] != "juz_byl":
                db.execute("DELETE FROM pliki WHERE sciezka=?", (w["cel"],))  # nie ma go już w bibliotece
            db.execute("UPDATE plan SET wynik=NULL WHERE id=?", (w["plan_id"],))
            cofniete += 1
        except OSError as e:
            bledy.append(str(e))
        zatwierdz()
    db.commit()
    granica = os.path.normcase(os.path.normpath(planista.meta(db).get("cel", "")))
    for f in sorted(foldery_celu, key=len, reverse=True):
        while f and os.path.normcase(os.path.normpath(f)) != granica and granica:
            try:
                os.rmdir(f)  # tylko puste
            except OSError:
                break
            f = os.path.dirname(f)
    return {"cofniete": cofniete, "bledy": bledy}
