"""Wykrywanie duplikatów po zawartości i bezpieczne odkładanie ich na bok (z cofaniem).

Etapy (każdy odsiewa kandydatów, żeby jak najmniej czytać przez sieć):
1. ten sam rozmiar (z bazy skanu, bez czytania plików),
2. szybki odcisk: 1 MB z początku + 1 MB z końca,
3. pełny odcisk całej zawartości (BLAKE2b) — dopiero on decyduje o duplikacie.
Odciski są zapamiętywane w bazie, więc ponowne wyszukiwanie jest natychmiastowe.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import indeks
from .skaner import Przerwano, Zatwierdzanie
from .stabilnosc import opis_bledu, tylko_w_chmurze

BLOK = 1 << 20
# Pełny odcisk dużych plików liczymy po jednym naraz: kilka równoległych długich odczytów z jednego dysku
# (zwłaszcza sieciowego z talerzem, np. WD My Cloud) to skakanie głowicy i wielokrotnie wolniejszy odczyt.
DUZY_PLIK = 64 * BLOK
FOLDER_ODLOZONE = "Odłożone"   # <korzeń>/Odłożone/{Duplikaty,Podobne,Nieostre}/<ścieżka>
PODFOLDERY = {"duplikat": "Duplikaty", "podobne": "Podobne", "nieostre": "Nieostre", "smieci": "Śmieci",
              "usuniete": "Usunięte"}
FOLDER_DUPLIKATOW = "_Duplikaty_Katalogator"  # do wersji 1.3 — nadal pomijany przy skanie

SCHEMAT = """
CREATE TABLE IF NOT EXISTS odciski (
    sciezka TEXT PRIMARY KEY,
    rozmiar INTEGER NOT NULL,
    mtime   REAL NOT NULL,
    szybki  TEXT,
    pelny   TEXT
);
CREATE INDEX IF NOT EXISTS ix_odciski_pelny ON odciski(pelny);
CREATE TABLE IF NOT EXISTS operacje (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    partia  INTEGER NOT NULL,
    czas    REAL NOT NULL,
    typ     TEXT NOT NULL,
    z_      TEXT NOT NULL,
    do_     TEXT NOT NULL,
    wiersz  TEXT NOT NULL,
    cofnieta INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS dup_meta (klucz TEXT PRIMARY KEY, wartosc TEXT);
"""

# Ścieżki, które zwykle są kopiami — plik z nich zostawiamy tylko w ostateczności.
_PODEJRZANE = re.compile(
    r"kopia|copy|duplikat|backup|kopie zapasowe|whatsapp|messenger|download|pobrane|"
    r"temp\b|tmp\b|\(\d+\)|odłożone|" + FOLDER_DUPLIKATOW.lower(),
    re.IGNORECASE,
)


def przygotuj(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMAT)


def _odcisk(sciezka: str, rozmiar: int, pelny: bool, przerwij=None, licz=None) -> str:
    h = hashlib.blake2b(digest_size=20)
    h.update(str(rozmiar).encode())
    with open(sciezka, "rb") as f:
        if pelny:
            while True:
                if przerwij is not None and przerwij.is_set():
                    raise Przerwano(sciezka)
                kawalek = f.read(4 * BLOK)
                if not kawalek:
                    break
                h.update(kawalek)
                if licz is not None:
                    licz(len(kawalek))
        else:
            h.update(f.read(BLOK))
            if rozmiar > 2 * BLOK:
                f.seek(-BLOK, os.SEEK_END)
                h.update(f.read(BLOK))
            if licz is not None:
                licz(min(rozmiar, 2 * BLOK))
    return h.hexdigest()


def szukaj(db: sqlite3.Connection, postep=None, przerwij=None, watki: int = 4) -> dict:
    """postep(etap, zrobione, wszystkie, bajty). Zwraca podsumowanie()."""
    przygotuj(db)
    from .stabilnosc import Straznik
    straznik = Straznik([r[0] for r in db.execute("SELECT DISTINCT korzen FROM pliki")], przerwij,
                        getattr(postep, "czeka", None))
    bajty = [0]
    razem = [0]
    biezacy = {"etap": "", "zrobione": 0, "wszystkie": 0, "t": 0.0, "plik": ""}
    jeden_duzy = threading.Lock()
    problemy = {"chmura": 0, "bledy": 0, "przyklad": ""}  # pliki pominięte — widać je w oknie

    def opis_problemow() -> str:
        t = []
        if problemy["chmura"]:
            t.append(f"{problemy['chmura']} plików tylko w chmurze (pominięte)")
        if problemy["bledy"]:
            t.append(f"nie da się odczytać {problemy['bledy']} plików — np. {problemy['przyklad']}")
        return "; ".join(t)

    def dod():
        d = {"bajty_razem": razem[0], **({"plik": biezacy["plik"]} if biezacy["plik"] else {})}
        if problemy["chmura"] or problemy["bledy"]:
            d["opis"] = "⚠ " + opis_problemow()
        return d

    def licz(n):  # wołane w trakcie czytania — pasek rusza się także przy jednym wielkim pliku
        bajty[0] += n
        teraz = time.monotonic()
        if postep is not None and teraz - biezacy["t"] > 0.5:
            biezacy["t"] = teraz
            postep(biezacy["etap"], biezacy["zrobione"], biezacy["wszystkie"], bajty[0], **dod())

    def zglos(etap, zrobione, wszystkie):
        biezacy.update(etap=etap, zrobione=zrobione, wszystkie=wszystkie)
        if postep is not None:
            postep(etap, zrobione, wszystkie, bajty[0], **dod())

    def policz(etap: str, wiersze: list, pelny: bool) -> None:
        kol = "pelny" if pelny else "szybki"
        bajty[0] = 0
        razem[0] = sum(w["rozmiar"] if pelny else min(w["rozmiar"], 2 * BLOK) for w in wiersze)
        zglos(etap, 0, len(wiersze))

        # wspólny indeks: odcisk policzony wcześniej (inny tryb / projekt) — bez czytania pliku
        gotowe = {s: r[kol] for s, r in indeks.pobierz("odciski", [(w["sciezka"], w["rozmiar"], w["mtime"])
                                                                   for w in wiersze]).items() if r[kol]}

        def zadanie(w):
            if przerwij is not None and przerwij.is_set():
                raise Przerwano(w["sciezka"])
            if w["sciezka"] in gotowe:
                return w, gotowe[w["sciezka"]]
            if tylko_w_chmurze(w["sciezka"]):  # otwarcie ściągałoby plik z internetu (albo kończyło się błędem)
                problemy["chmura"] += 1
                return w, None
            try:
                if pelny and w["rozmiar"] >= DUZY_PLIK:
                    with jeden_duzy:  # duże pliki po kolei — odczyt ciągły zamiast skakania po dysku
                        if przerwij is not None and przerwij.is_set():
                            raise Przerwano(w["sciezka"])
                        biezacy["plik"] = w["sciezka"]
                        try:
                            return w, straznik.wykonaj(_odcisk, w["sciezka"], w["sciezka"], w["rozmiar"], True,
                                                       przerwij, licz)
                        finally:
                            biezacy["plik"] = ""
                return w, straznik.wykonaj(_odcisk, w["sciezka"], w["sciezka"], w["rozmiar"], pelny, przerwij, licz)
            except Przerwano:
                raise
            except OSError as e:  # plik zniknął / brak dostępu — pomijamy, ale widać to w oknie
                problemy["bledy"] += 1
                if not problemy["przyklad"]:
                    problemy["przyklad"] = f"„{os.path.basename(w['sciezka'])}”: {opis_bledu(e)}"
                return w, None

        zatwierdz = Zatwierdzanie(db)
        nowe_do_indeksu: list = []
        with ThreadPoolExecutor(max_workers=watki) as pula:
            for i, (w, odc) in enumerate(pula.map(zadanie, wiersze), 1):
                if odc is not None:
                    db.execute(
                        "INSERT INTO odciski(sciezka, rozmiar, mtime) VALUES (?,?,?) "
                        "ON CONFLICT(sciezka) DO UPDATE SET rozmiar=excluded.rozmiar, mtime=excluded.mtime, "
                        "szybki=CASE WHEN odciski.rozmiar=excluded.rozmiar AND odciski.mtime=excluded.mtime "
                        "THEN odciski.szybki END, pelny=CASE WHEN odciski.rozmiar=excluded.rozmiar "
                        "AND odciski.mtime=excluded.mtime THEN odciski.pelny END",
                        (w["sciezka"], w["rozmiar"], w["mtime"]),
                    )
                    db.execute(f"UPDATE odciski SET {kol}=? WHERE sciezka=?", (odc, w["sciezka"]))
                    if w["sciezka"] not in gotowe:
                        nowe_do_indeksu.append((w, odc))
                    # mały plik przeczytany w całości: szybki odcisk = pełny
                    if not pelny and w["rozmiar"] <= 2 * BLOK:
                        db.execute("UPDATE odciski SET pelny=? WHERE sciezka=?", (odc, w["sciezka"]))
                zatwierdz(wymus=pelny)  # pełny odcisk dużego pliku trwa długo — zapisuj od razu
                if i % 20 == 0:
                    zglos(etap, i, len(wiersze))
        db.commit()
        if nowe_do_indeksu and indeks.wlaczony():
            znane = indeks.pobierz("odciski", [(w["sciezka"], w["rozmiar"], w["mtime"]) for w, _ in nowe_do_indeksu])
            wpisy = []
            for w, odc in nowe_do_indeksu:
                stare = znane.get(w["sciezka"], {})
                d = {"sciezka": w["sciezka"], "rozmiar": w["rozmiar"], "mtime": w["mtime"],
                     "szybki": stare.get("szybki"), "pelny": stare.get("pelny")}
                d[kol] = odc
                if not pelny and w["rozmiar"] <= 2 * BLOK:
                    d["pelny"] = odc  # mały plik przeczytany w całości
                wpisy.append(d)
            indeks.zapisz("odciski", wpisy)
        zglos(etap, len(wiersze), len(wiersze))

    aktualny = "o.rozmiar = p.rozmiar AND o.mtime = p.mtime"
    try:
        # 1+2: pliki o powtarzającym się rozmiarze, bez aktualnego szybkiego odcisku
        brak_szybkiego = db.execute(
            f"""SELECT p.sciezka, p.rozmiar, p.mtime FROM pliki p
                LEFT JOIN odciski o ON o.sciezka = p.sciezka AND {aktualny}
                WHERE p.rozmiar > 0 AND o.szybki IS NULL AND p.rozmiar IN
                  (SELECT rozmiar FROM pliki WHERE rozmiar > 0 GROUP BY rozmiar HAVING COUNT(*) > 1)"""
        ).fetchall()
        policz("szybkie porównanie", brak_szybkiego, pelny=False)
        # 3: pełny odcisk tylko tam, gdzie szybki się powtarza
        brak_pelnego = db.execute(
            f"""SELECT p.sciezka, p.rozmiar, p.mtime FROM pliki p
                JOIN odciski o ON o.sciezka = p.sciezka AND {aktualny}
                WHERE o.pelny IS NULL AND (p.rozmiar, o.szybki) IN
                  (SELECT p2.rozmiar, o2.szybki FROM pliki p2
                   JOIN odciski o2 ON o2.sciezka = p2.sciezka AND o2.rozmiar = p2.rozmiar AND o2.mtime = p2.mtime
                   WHERE o2.szybki IS NOT NULL GROUP BY p2.rozmiar, o2.szybki HAVING COUNT(*) > 1)
                ORDER BY p.rozmiar"""
        ).fetchall()
        policz("dokładne sprawdzanie", brak_pelnego, pelny=True)
        # zapamiętaj, że szukano (także gdy nic nie znaleziono — okno pokaże „brak duplikatów”, nie „nie szukano”)
        db.execute("INSERT OR REPLACE INTO dup_meta VALUES ('ostatnie_szukanie', ?)", (str(time.time()),))
    finally:
        db.commit()
    return {**podsumowanie(db), "problemy": opis_problemow()}


def szukano(db: sqlite3.Connection) -> bool:
    przygotuj(db)
    return db.execute("SELECT 1 FROM dup_meta WHERE klucz='ostatnie_szukanie'").fetchone() is not None \
        or db.execute("SELECT 1 FROM odciski LIMIT 1").fetchone() is not None


_GRUPY = """
    SELECT o.pelny h, p.rozmiar, COUNT(*) n FROM pliki p
    JOIN odciski o ON o.sciezka = p.sciezka AND o.rozmiar = p.rozmiar AND o.mtime = p.mtime
    WHERE o.pelny IS NOT NULL GROUP BY o.pelny HAVING COUNT(*) > 1
"""


def podsumowanie(db: sqlite3.Connection) -> dict:
    przygotuj(db)
    r = db.execute(
        f"SELECT COUNT(*) grupy, COALESCE(SUM(n-1),0) nadmiar, COALESCE(SUM((n-1)*rozmiar),0) bajty FROM ({_GRUPY})"
    ).fetchone()
    wg = db.execute(
        f"""SELECT p.rodzaj, COUNT(DISTINCT g.h) grupy FROM ({_GRUPY}) g
            JOIN odciski o ON o.pelny = g.h JOIN pliki p ON p.sciezka = o.sciezka
            GROUP BY p.rodzaj"""
    ).fetchall()
    return {"grupy": r["grupy"], "nadmiar": r["nadmiar"], "bajty": r["bajty"],
            "rodzaje": {w["rodzaj"]: w["grupy"] for w in wg}}


def _ocena(plik: dict, cele: set[str]) -> tuple:
    """Mniejsza = lepszy kandydat do ZOSTAWIENIA."""
    podejrzana = len(_PODEJRZANE.findall(plik["wzgledna"]))
    w_celu = 0 if plik["korzen"] in cele else 1  # to, co już jest w miejscu docelowym, zostaje
    return (podejrzana, w_celu, plik["mtime"], len(plik["wzgledna"]), plik["wzgledna"])


_PAMIEC_GRUP: dict = {}


def _odcisk_stanu(db: sqlite3.Connection) -> tuple:
    """Tani „odcisk” plików i odcisków — zmienia się po skanie, szukaniu, odłożeniu i porządkowaniu."""
    plik = next((r[2] for r in db.execute("PRAGMA database_list") if r[1] == "main"), "")
    return (plik or id(db),
            *db.execute("SELECT COUNT(*), MAX(rowid), TOTAL(rowid), TOTAL(mtime), TOTAL(rozmiar) FROM pliki").fetchone(),
            *db.execute("SELECT COUNT(*), TOTAL(rowid), COUNT(pelny), MAX(pelny), MIN(pelny) FROM odciski").fetchone())


def grupy(db: sqlite3.Connection, rodzaj: str | None = None, od: int = 0, ile: int = 50,
          cele: set[str] | None = None) -> list[dict]:
    przygotuj(db)
    cele = cele or set()
    filtr, arg = "", []
    if rodzaj:
        filtr = "WHERE EXISTS (SELECT 1 FROM odciski o3 JOIN pliki p3 ON p3.sciezka=o3.sciezka " \
                "WHERE o3.pelny = g.h AND p3.rodzaj = ?)"
        arg.append(rodzaj)
    # lista grup (przy 200 tys. plików liczy się ponad sekundę) jest pamiętana — kolejne strony są natychmiast
    klucz = (_odcisk_stanu(db), rodzaj)
    if _PAMIEC_GRUP.get("klucz") != klucz:
        _PAMIEC_GRUP.clear()
        _PAMIEC_GRUP.update(klucz=klucz, naglowki=[tuple(r) for r in db.execute(
            f"SELECT g.h, g.rozmiar, g.n FROM ({_GRUPY}) g {filtr} ORDER BY (g.n - 1) * g.rozmiar DESC, g.h",
            arg)])
    naglowki = [dict(zip(("h", "rozmiar", "n"), r)) for r in _PAMIEC_GRUP["naglowki"][od:od + ile]]
    wynik = []
    for g in naglowki:
        pliki = [dict(r) for r in db.execute(
            """SELECT p.rowid id, p.sciezka, p.korzen, p.wzgledna, p.mtime, p.data, p.rodzaj
               FROM pliki p JOIN odciski o ON o.sciezka = p.sciezka AND o.rozmiar = p.rozmiar AND o.mtime = p.mtime
               WHERE o.pelny = ?""", (g["h"],))]
        pliki.sort(key=lambda p: _ocena(p, cele))
        wynik.append({
            "h": g["h"], "rozmiar": g["rozmiar"], "n": g["n"], "rodzaj": pliki[0]["rodzaj"],
            "zostaw": pliki[0]["id"], "pliki": pliki,
        })
    return wynik


def _cel_przeniesienia(korzen: str, wzgledna: str, typ: str = "duplikat") -> str:
    cel = os.path.join(korzen, FOLDER_ODLOZONE, PODFOLDERY.get(typ, "Inne"), wzgledna)
    baza, ext = os.path.splitext(cel)
    i = 2
    while os.path.exists(cel):
        cel = f"{baza} ({i}){ext}"
        i += 1
    return cel


def przenies(db: sqlite3.Connection, decyzje: list[dict]) -> dict:
    """decyzje: [{"zostaw": id, "usun": [id, ...]}]. Przenosi do <korzeń>/Odłożone/Duplikaty/."""
    przygotuj(db)
    partia = int(time.time() * 1000)
    przeniesione, pominiete, bajty = 0, [], 0
    for d in decyzje:
        ids = [d["zostaw"], *d.get("usun", [])]
        if d["zostaw"] in d.get("usun", []) or not d.get("usun"):
            continue
        wiersze = {r["rowid"]: r for r in db.execute(
            f"SELECT rowid, * FROM pliki WHERE rowid IN ({','.join('?' * len(ids))})", ids)}
        if len(wiersze) != len(set(ids)):
            pominiete.append("Grupa nieaktualna — przeskanuj ponownie.")
            continue
        odciski = [r[0] for r in db.execute(
            f"SELECT o.pelny FROM odciski o JOIN pliki p ON p.sciezka=o.sciezka AND o.rozmiar=p.rozmiar "
            f"AND o.mtime=p.mtime WHERE p.rowid IN ({','.join('?' * len(ids))})", ids)]
        # każdy plik musi mieć aktualny pełny odcisk i wszystkie muszą być równe
        if len(odciski) != len(set(ids)) or None in odciski or len(set(odciski)) != 1:
            pominiete.append("Pliki w grupie nie są identyczne — pominięto.")
            continue
        zostaw = wiersze[d["zostaw"]]
        try:
            st = os.stat(zostaw["sciezka"])
            if st.st_size != zostaw["rozmiar"]:
                raise OSError("zmieniony")
        except OSError:
            pominiete.append(f"Nie ma pliku do zostawienia: {zostaw['wzgledna']}")
            continue
        for i in d["usun"]:
            try:  # ten sam plik widziany dwa razy (ten sam folder pod dwiema nazwami) — to nie kopia
                if os.path.samefile(zostaw["sciezka"], wiersze[i]["sciezka"]):
                    pominiete.append(f"To ten sam plik (ten sam folder dodany dwa razy?): {wiersze[i]['wzgledna']}")
                    continue
            except OSError:
                pass
            blad = _odloz_wiersz(db, wiersze[i], partia, "duplikat")
            if blad:
                pominiete.append(blad)
            else:
                przeniesione += 1
                bajty += wiersze[i]["rozmiar"]
        db.commit()
    return {"przeniesione": przeniesione, "bajty": bajty, "pominiete": pominiete, "partia": partia}


def _odloz_wiersz(db: sqlite3.Connection, w, partia: int, typ: str) -> str | None:
    """Przenosi plik do <korzeń>/Odłożone/<Duplikaty|Podobne|Nieostre>/<ścieżka>. Zwraca opis błędu albo None."""
    try:
        st = os.stat(w["sciezka"])
        if (st.st_size, st.st_mtime) != (w["rozmiar"], w["mtime"]):
            return f"Zmieniony od skanu: {w['wzgledna']}"
        cel = _cel_przeniesienia(w["korzen"], w["wzgledna"], typ)
        os.makedirs(os.path.dirname(cel), exist_ok=True)
        os.rename(w["sciezka"], cel)
    except OSError as e:
        return f"{w['wzgledna']}: {e.strerror or e}"
    dane = {k: w[k] for k in w.keys() if k != "rowid"}
    dane["_rowid"] = w["rowid"]  # przy cofaniu plik wraca z tym samym numerem (miniatury, propozycja drzewa)
    db.execute("INSERT INTO operacje(partia, czas, typ, z_, do_, wiersz) VALUES (?,?,?,?,?,?)",
               (partia, time.time(), typ, w["sciezka"], cel, json.dumps(dane, ensure_ascii=False)))
    db.execute("DELETE FROM pliki WHERE rowid = ?", (w["rowid"],))
    return None


def odloz(db: sqlite3.Connection, ids: list[int], typ: str) -> dict:
    """Odkłada wskazane pliki (np. podobne / nieostre zdjęcia) — bez wymogu identyczności."""
    przygotuj(db)
    partia = int(time.time() * 1000)
    przeniesione, pominiete, bajty = 0, [], 0
    for i in dict.fromkeys(int(x) for x in ids):
        w = db.execute("SELECT rowid, * FROM pliki WHERE rowid=?", (i,)).fetchone()
        if not w:
            pominiete.append("Plik nieaktualny — przeskanuj ponownie.")
            continue
        blad = _odloz_wiersz(db, w, partia, typ)
        if blad:
            pominiete.append(blad)
        else:
            przeniesione += 1
            bajty += w["rozmiar"]
    db.commit()
    return {"przeniesione": przeniesione, "bajty": bajty, "pominiete": pominiete, "partia": partia}


def ostatnia_partia(db: sqlite3.Connection) -> dict | None:
    przygotuj(db)
    r = db.execute(
        "SELECT partia, COUNT(*) n, MIN(czas) czas, MIN(typ) typ FROM operacje WHERE cofnieta = 0 "
        "GROUP BY partia ORDER BY partia DESC LIMIT 1").fetchone()
    return dict(r) if r else None


def cofnij(db: sqlite3.Connection, partia: int | None = None) -> dict:
    """Przywraca pliki z ostatniej nie cofniętej operacji (albo ze wskazanej partii)."""
    ost = ostatnia_partia(db) if partia is None else {"partia": int(partia)}
    if not ost:
        return {"przywrocone": 0, "bledy": []}
    przywrocone, bledy = 0, []
    for op in db.execute("SELECT * FROM operacje WHERE partia = ? AND cofnieta = 0", (ost["partia"],)).fetchall():
        try:
            if os.path.exists(op["z_"]):
                raise OSError(f"w miejscu oryginału jest już plik: {op['z_']}")
            os.makedirs(os.path.dirname(op["z_"]), exist_ok=True)
            os.rename(op["do_"], op["z_"])
        except OSError as e:
            bledy.append(str(e))
            continue
        w = json.loads(op["wiersz"])
        rowid = w.pop("_rowid", None)
        if rowid is not None and not db.execute("SELECT 1 FROM pliki WHERE rowid=?", (rowid,)).fetchone():
            w["rowid"] = rowid
        db.execute(f"INSERT OR REPLACE INTO pliki({','.join(w)}) VALUES ({','.join('?' * len(w))})", list(w.values()))
        db.execute("UPDATE operacje SET cofnieta = 1 WHERE id = ?", (op["id"],))
        przywrocone += 1
    db.commit()
    _usun_puste(db, ost["partia"])
    return {"przywrocone": przywrocone, "bledy": bledy, "partia": ost["partia"]}


def _usun_puste(db: sqlite3.Connection, partia: int) -> None:
    """Sprząta puste podfoldery w Odłożone (i dawnym _Duplikaty_Katalogator) po cofnięciu."""
    granice = (FOLDER_ODLOZONE, FOLDER_DUPLIKATOW)
    for (do_,) in db.execute("SELECT do_ FROM operacje WHERE partia = ?", (partia,)):
        folder = os.path.dirname(do_)
        while any(g in folder for g in granice):
            try:
                os.rmdir(folder)
            except OSError:
                break
            if os.path.basename(folder) in granice:
                break
            folder = os.path.dirname(folder)
