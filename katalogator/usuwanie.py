"""„🗑 Usuń” — wszędzie, gdzie widać plik (Biblioteka, Przeglądarka, zakładki projektu, telefon).

Plik nie znika od razu: trafia do kosza programu `<folder>/Odłożone/Usunięte/<ścieżka>` (działa też na dyskach
sieciowych, gdzie nie ma Kosza Windows) i można go jednym kliknięciem przywrócić. Na stałe — Sprzątanie → Usuwanie.
"""

from __future__ import annotations

import sqlite3

from . import duplikaty

UWAGA = "Usunięty (Odłożone/Usunięte)"


def _plan(db: sqlite3.Connection) -> bool:
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='plan'").fetchone())


def usun(db: sqlite3.Connection, ids: list[int]) -> dict:
    w = duplikaty.odloz(db, ids, "usuniete")
    usuniete = [s for (s,) in db.execute("SELECT z_ FROM operacje WHERE partia=?", (w["partia"],))]
    if usuniete and _plan(db):  # propozycja drzewa: usuniętego pliku nie porządkujemy
        for i in range(0, len(usuniete), 500):
            cz = usuniete[i:i + 500]
            db.execute(f"UPDATE plan SET pominiety=1, uwaga=? WHERE wynik IS NULL AND pominiety=0 AND sciezka IN "
                       f"({','.join('?' * len(cz))})", [UWAGA, *cz])
        db.commit()
    return {**w, "usuniete": w["przeniesione"]}


def cofnij(db: sqlite3.Connection, partia: int) -> dict:
    w = duplikaty.cofnij(db, partia)
    if w["przywrocone"] and _plan(db):
        przywr = [s for (s,) in db.execute("SELECT z_ FROM operacje WHERE partia=? AND cofnieta=1", (int(partia),))]
        for i in range(0, len(przywr), 500):
            cz = przywr[i:i + 500]
            db.execute(f"UPDATE plan SET pominiety=0, uwaga=NULL WHERE uwaga=? AND sciezka IN "
                       f"({','.join('?' * len(cz))})", [UWAGA, *cz])
        db.commit()
    return w
