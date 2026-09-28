"""Punkt startowy Katalogator.exe (PyInstaller)."""

import sys

from katalogator.__main__ import main

if __name__ == "__main__":
    # bez parametrów: okno aplikacji; „--auto <projekt>”: porządkowanie folderu przychodzącego (harmonogram)
    sys.exit(main(sys.argv[1:]))
