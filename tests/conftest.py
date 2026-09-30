import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


import pytest


@pytest.fixture(autouse=True)
def _bez_wspolnego_indeksu():
    """Każdy test zaczyna bez wspólnego indeksu odczytów (Stan() go włącza — nie może przeciekać do innych testów)."""
    from katalogator import indeks
    indeks.ustaw(None)
    yield
    indeks.ustaw(None)
