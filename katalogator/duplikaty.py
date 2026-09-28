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
import time
from concurrent.futures import ThreadPoolExecutor

from .skaner import Przerwano

BLOK = 1 << 20
FOLDER_DUPLIKATOW = "_Duplikaty_Katalogator"

SCHEMAT = """
CREATE TABLE IF NOT EXISTS odciski (
    sciezka TEXT PRIMARY KEY,
    rozmiar INTEGER NOT NULL,
    mtime   REAL NOT NULL,
    szybki  TEXT,
    pelny   TEXT
);
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
"""

# Ścieżki, które zwykle są kopiami — plik z nich zostawiamy tylko w ostateczności.
_PODEJRZANE = re.compile(
    r"kopia|copy|duplikat|backup|kopie zapasowe|whatsapp|messenger|download|pobrane|"
    r"temp\b|tmp\b|\(\d+\)|" + FOLDER_DUPLIKATOW.lower(),
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
    bajty = [0]

    def licz(n):
        bajty[0] += n

    def zglos(etap, zrobione, wszystkie):
        if postep is not None:
            postep(etap, zrobione, wszystkie, bajty[0])

    def policz(etap: str, wiersze: list, pelny: bool) -> None:
        kol = "pelny" if pelny else "szybki"
        zglos(etap, 0, len(wiersze))

        def zadanie(w):
            if przerwij is not None and przerwij.is_set():
                raise Przerwano(w["sciezka"])
            try:
                return w, _odcisk(w["sciezka"], w["rozmiar"], pelny, przerwij, licz)
            except OSError:
                return w, None  # plik zniknął / brak dostępu — pomijamy

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
                    # mały plik przeczytany w całości: szybki odcisk = pełny
                    if not pelny and w["rozmiar"] <= 2 * BLOK:
                        db.execute("UPDATE odciski SET pelny=? WHERE sciezka=?", (odc, w["sciezka"]))
                if i % 50 == 0:
                    db.commit()
                    zglos(etap, i, len(wiersze))
        db.commit()
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
    finally:
        db.commit()
    return podsumowanie(db)


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


def grupy(db: sqlite3.Connection, rodzaj: str | None = None, od: int = 0, ile: int = 50,
          cele: set[str] | None = None) -> list[dict]:
    przygotuj(db)
    cele = cele or set()
    filtr, arg = "", []
    if rodzaj:
        filtr = "WHERE EXISTS (SELECT 1 FROM odciski o3 JOIN pliki p3 ON p3.sciezka=o3.sciezka " \
                "WHERE o3.pelny = g.h AND p3.rodzaj = ?)"
        arg.append(rodzaj)
    naglowki = db.execute(
        f"SELECT g.h, g.rozmiar, g.n FROM ({_GRUPY}) g {filtr} "
        f"ORDER BY (g.n - 1) * g.rozmiar DESC, g.h LIMIT ? OFFSET ?",
        [*arg, ile, od],
    ).fetchall()
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


def _cel_przeniesienia(korzen: str, wzgledna: str) -> str:
    cel = os.path.join(korzen, FOLDER_DUPLIKATOW, wzgledna)
    baza, ext = os.path.splitext(cel)
    i = 2
    while os.path.exists(cel):
        cel = f"{baza} ({i}){ext}"
        i += 1
    return cel


def przenies(db: sqlite3.Connection, decyzje: list[dict]) -> dict:
    """decyzje: [{"zostaw": id, "usun": [id, ...]}]. Przenosi do <korzeń>/_Duplikaty_Katalogator/."""
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
            w = wiersze[i]
            try:
                st = os.stat(w["sciezka"])
                if (st.st_size, st.st_mtime) != (w["rozmiar"], w["mtime"]):
                    pominiete.append(f"Zmieniony od skanu: {w['wzgledna']}")
                    continue
                cel = _cel_przeniesienia(w["korzen"], w["wzgledna"])
                os.makedirs(os.path.dirname(cel), exist_ok=True)
                os.rename(w["sciezka"], cel)
            except OSError as e:
                pominiete.append(f"{w['wzgledna']}: {e.strerror or e}")
                continue
            dane = {k: w[k] for k in w.keys() if k != "rowid"}
            db.execute("INSERT INTO operacje(partia, czas, typ, z_, do_, wiersz) VALUES (?,?,?,?,?,?)",
                       (partia, time.time(), "duplikat", w["sciezka"], cel, json.dumps(dane, ensure_ascii=False)))
            db.execute("DELETE FROM pliki WHERE rowid = ?", (i,))
            przeniesione += 1
            bajty += w["rozmiar"]
        db.commit()
    return {"przeniesione": przeniesione, "bajty": bajty, "pominiete": pominiete, "partia": partia}


def ostatnia_partia(db: sqlite3.Connection) -> dict | None:
    przygotuj(db)
    r = db.execute(
        "SELECT partia, COUNT(*) n, MIN(czas) czas FROM operacje WHERE cofnieta = 0 AND typ = 'duplikat' "
        "GROUP BY partia ORDER BY partia DESC LIMIT 1").fetchone()
    return dict(r) if r else None


def cofnij(db: sqlite3.Connection) -> dict:
    """Przywraca pliki z ostatniej nie cofniętej operacji."""
    ost = ostatnia_partia(db)
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
        db.execute(f"INSERT OR REPLACE INTO pliki({','.join(w)}) VALUES ({','.join('?' * len(w))})", list(w.values()))
        db.execute("UPDATE operacje SET cofnieta = 1 WHERE id = ?", (op["id"],))
        przywrocone += 1
    db.commit()
    _usun_puste(db, ost["partia"])
    return {"przywrocone": przywrocone, "bledy": bledy}


def _usun_puste(db: sqlite3.Connection, partia: int) -> None:
    """Sprząta puste podfoldery w _Duplikaty_Katalogator po cofnięciu."""
    for (do_,) in db.execute("SELECT do_ FROM operacje WHERE partia = ?", (partia,)):
        folder = os.path.dirname(do_)
        while FOLDER_DUPLIKATOW in folder:
            try:
                os.rmdir(folder)
            except OSError:
                break
            if os.path.basename(folder) == FOLDER_DUPLIKATOW:
                break
            folder = os.path.dirname(folder)
