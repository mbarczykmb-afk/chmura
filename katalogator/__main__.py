"""Bez parametrów: aplikacja okienkowa. Z parametrami: python -m katalogator skanuj|raport ..."""

import argparse
import os
import sys
import webbrowser
from pathlib import Path

from . import raport, skaner


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if sys.stdout is None:  # Katalogator.exe bez konsoli (UTF-8, bo domyślne cp1252 nie zna polskich znaków)
        sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")
    if args[:1] in (["--auto"], ["--usun-harmonogramy"]) or not args:
        # tryby bez konsoli: wszystko (także błędy) do pliku dziennika, nigdy okienko z błędem
        from . import logi
        from .aplikacja import katalog_danych
        katalog = katalog_danych()
        logi.konfiguruj(katalog)
        try:
            if args[:1] == ["--auto"] and len(args) == 2:
                from .przychodzace import automat
                logi.LOG.info("Tryb automatyczny: projekt %s", args[1])
                wynik = automat(katalog, args[1])
                logi.LOG.info("Tryb automatyczny zakończony: %s", wynik)
                try:
                    print(wynik)
                except (UnicodeError, OSError):
                    pass  # konsola bez polskich znaków — wynik i tak jest w dzienniku
                return 0
            if args[:1] == ["--usun-harmonogramy"]:
                from .przychodzace import usun_wszystkie_harmonogramy
                usun_wszystkie_harmonogramy(katalog)
                return 0
            if not args:
                from .aplikacja import main as aplikacja  # bez parametrów: okno aplikacji
                aplikacja()
                return 0
            return 2
        except Exception:
            logi.LOG.exception("Błąd programu (parametry: %s)", args)
            return 1
    if not args:
        from .aplikacja import main as aplikacja  # bez parametrów: okno aplikacji
        aplikacja()
        return 0
    p = argparse.ArgumentParser(prog="katalogator", description="Porządkowanie zdjęć, filmów, muzyki i plików.")
    p.add_argument("--baza", default="katalog.db", help="plik bazy skanu (domyślnie katalog.db)")
    sub = p.add_subparsers(dest="polecenie", required=True)

    s = sub.add_parser("skanuj", help="skanuj foldery (można przerwać i wznowić)")
    s.add_argument("foldery", nargs="+", help="np. Z:\\ albo \\\\192.168.1.50\\Public")
    s.add_argument("--watki", type=int, default=8, help="równoległe odczyty (domyślnie 8)")
    s.add_argument("--bez-raportu", action="store_true")

    r = sub.add_parser("raport", help="pokaż raport z ostatniego skanu")
    r.add_argument("--html", default="raport.html", help="plik raportu HTML")
    r.add_argument("--nie-otwieraj", action="store_true")

    a = p.parse_args(argv)
    db = skaner.otworz_baze(a.baza)

    if a.polecenie == "skanuj":
        for folder in a.foldery:
            print(f"Skanuję {folder} ...")
            try:
                w = skaner.skanuj(folder, db, watki=a.watki)
            except NotADirectoryError:
                print(f"  Nie ma takiego folderu: {folder}", file=sys.stderr)
                return 1
            except KeyboardInterrupt:
                db.commit()
                print("\nPrzerwano — postęp zapisany, uruchom ponownie, aby dokończyć.")
                return 130
            print(f"  Plików: {w['wszystkie']} (nowe/zmienione: {w['nowe_lub_zmienione']}, "
                  f"bez zmian: {w['bez_zmian']}); pominięte śmieci: {w['pominiete_pliki']}")
        if a.bez_raportu:
            return 0
        a.html, a.nie_otwieraj = "raport.html", False

    dane = raport.zbierz(db)
    print()
    print(raport.tekst(dane))
    sciezka = Path(a.html).resolve()
    sciezka.write_text(raport.html_raport(dane), encoding="utf-8")
    print(f"\nRaport HTML: {sciezka}")
    if not a.nie_otwieraj:
        webbrowser.open(sciezka.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
