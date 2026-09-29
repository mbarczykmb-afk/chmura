"""Stabilizator długich zadań (dziesiątki tysięcy plików, dziesiątki GB przez sieć).

- `Straznik` — gdy dysk sieciowy (WD My Cloud, NAS) na chwilę zniknie, zadanie nie zalewa się
  błędami, tylko czeka, aż dysk wróci, i ponawia operację na tym samym pliku;
- `Czuwanie` — komputer nie przechodzi w uśpienie w trakcie zadania (Windows);
- `Tempo` — prędkość i szacowany czas do końca liczone z ostatniej minuty pracy.
"""

from __future__ import annotations

import collections
import errno
import os
import sys
import threading
import time

from .skaner import Przerwano

CZEKAJ_MAKS = 15 * 60   # tyle najdłużej czekamy na powrót dysku, potem zadanie się zatrzymuje (postęp zostaje)
SPRAWDZAJ_CO = 5
# błędy dotyczące samego pliku — ponawianie nic nie da
_BLEDY_PLIKU = (FileNotFoundError, PermissionError, FileExistsError, IsADirectoryError, NotADirectoryError)


def _dostepny(sciezka: str) -> bool:
    try:
        return os.path.isdir(sciezka)
    except OSError:
        return False


class Straznik:
    """Pilnuje dostępu do folderów głównych (źródła, cel).

    zglos(tekst | None) — komunikat „czekam na dysk…” dla okna (None = znów jest dostęp)."""

    def __init__(self, korzenie, przerwij: threading.Event | None = None, zglos=None,
                 czekaj_maks: float = CZEKAJ_MAKS, sprawdzaj_co: float = SPRAWDZAJ_CO, pauza: float = 2.0):
        self.korzenie = sorted({os.path.abspath(k) for k in korzenie if k}, key=len, reverse=True)
        self.przerwij, self.zglos = przerwij, zglos
        self.czekaj_maks, self.sprawdzaj_co, self.pauza = czekaj_maks, sprawdzaj_co, pauza
        self.przerwy = 0          # ile razy dysk znikał
        self._blokada = threading.Lock()

    def korzen(self, sciezka: str) -> str | None:
        s = os.path.normcase(os.path.abspath(sciezka))
        for k in self.korzenie:
            kk = os.path.normcase(k)
            if s == kk or s.startswith(kk.rstrip("\\/") + os.sep):
                return k
        return None

    def _spij(self, s: float) -> None:
        if self.przerwij is not None:
            if self.przerwij.wait(s):
                raise Przerwano("przerwano podczas oczekiwania na dysk")
        else:
            time.sleep(s)

    def czekaj_na(self, korzen: str) -> bool:
        """Czeka, aż folder główny znów będzie dostępny. False = był dostępny od razu."""
        if _dostepny(korzen):
            return False
        with self._blokada:  # czeka jeden wątek, pozostałe stoją za nim
            start = time.monotonic()
            self.przerwy += 1
            while not _dostepny(korzen):
                minelo = time.monotonic() - start
                if minelo > self.czekaj_maks:
                    if self.zglos:
                        self.zglos(None)
                    raise OSError(errno.EHOSTDOWN,
                                  f"Brak dostępu do {korzen} od {int(self.czekaj_maks // 60)} min. "
                                  "Postęp jest zapisany — sprawdź połączenie z dyskiem i uruchom zadanie ponownie")
                if self.zglos:
                    self.zglos(f"Utracono dostęp do {korzen} — czekam, aż wróci ({int(minelo)} s)…")
                self._spij(self.sprawdzaj_co)
            if self.zglos:
                self.zglos(None)
        return True

    def wykonaj(self, f, sciezka: str, *a, proby: int = 3, **kw):
        """f(*a, **kw) z ponawianiem, gdy błąd wynika z utraty dostępu do dysku."""
        for proba in range(proby):
            try:
                return f(*a, **kw)
            except Przerwano:
                raise
            except OSError as e:
                if proba == proby - 1:
                    raise
                k = self.korzen(sciezka)
                if k and self.czekaj_na(k):
                    continue          # dysk wrócił — ponów ten sam plik
                if isinstance(e, _BLEDY_PLIKU) or e.errno is None:
                    raise  # błąd samego pliku (np. uszkodzony obraz) — ponawianie nic nie da
                self._spij(self.pauza)  # chwilowa czkawka sieci — jeszcze jedna próba
        return None  # pragma: no cover

    def utracono(self, *sciezki: str) -> bool:
        """Po błędzie: czy przyczyną był brak dostępu do dysku? Jeśli tak — czeka, aż wróci, i zwraca True
        (operację można powtórzyć). False = dyski są dostępne, błąd dotyczy samego pliku."""
        wynik = False
        for s in sciezki:
            k = self.korzen(s)
            if k and self.czekaj_na(k):
                wynik = True
        return wynik

    def dostepny(self, sciezka: str) -> bool:
        """Czy folder główny tej ścieżki jest dostępny (a gdy nie — poczekaj na niego)."""
        k = self.korzen(sciezka)
        if k:
            self.czekaj_na(k)
        return True


class Czuwanie:
    """Na czas zadania: komputer nie usypia się sam (ekran może zgasnąć). Wywoływać w wątku zadania."""
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001

    def __enter__(self):
        self._ustaw(self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED)
        return self

    def __exit__(self, *a):
        self._ustaw(self.ES_CONTINUOUS)
        return False

    @staticmethod
    def _ustaw(flagi: int) -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(flagi)
        except Exception:
            pass


class Tempo:
    """Tempo i czas do końca z ostatnich ~90 s (prędkość sieci się zmienia)."""
    OKNO = 90.0

    def __init__(self):
        self.start = time.time()
        self.probki: collections.deque = collections.deque()

    def dodaj(self, ulamek: float, zrobione: int, bajty: int, teraz: float | None = None) -> None:
        teraz = time.time() if teraz is None else teraz
        if self.probki and teraz - self.probki[-1][0] < 1.0:
            self.probki[-1] = (self.probki[-1][0], ulamek, zrobione, bajty)
            return
        self.probki.append((teraz, ulamek, zrobione, bajty))
        while len(self.probki) > 2 and teraz - self.probki[0][0] > self.OKNO:
            self.probki.popleft()

    def wynik(self, teraz: float | None = None) -> dict:
        teraz = time.time() if teraz is None else teraz
        w = {"uplynelo": int(teraz - self.start)}
        if len(self.probki) < 2:
            return w
        (t0, u0, z0, b0), (t1, u1, z1, b1) = self.probki[0], self.probki[-1]
        dt = t1 - t0
        if dt < 3:
            return w
        if b1 > b0:
            w["bajty_s"] = int((b1 - b0) / dt)
        if z1 > z0:
            w["plikow_s"] = round((z1 - z0) / dt, 1)
        if u1 > u0 and 0 < u1 < 1:
            w["eta"] = int((1 - u1) / ((u1 - u0) / dt))
        return w
