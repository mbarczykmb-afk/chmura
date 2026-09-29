"""Rozpoznawanie rodzaju pliku i plików/folderów do pominięcia."""

from pathlib import PurePath

ZDJECIA = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".bmp",
    ".tif", ".tiff", ".dng", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2", ".raf",
}
FILMY = {
    ".mp4", ".mov", ".m4v", ".3gp", ".avi", ".mkv", ".wmv", ".mts", ".m2ts",
    ".mpg", ".mpeg", ".webm", ".flv", ".vob",
}
MUZYKA = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".wma", ".ape"}
# Pliki towarzyszące innym (napisy, sidecar), przenoszone razem z "rodzicem".
TOWARZYSZACE = {".xmp", ".aae", ".srt", ".sub", ".ass", ".ssa", ".thm", ".lrc"}

SMIECI_PLIKI = {"thumbs.db", "desktop.ini", ".ds_store", "ehthumbs.db"}
SMIECI_FOLDERY = {
    ".wdmc", "@eadir", "$recycle.bin", "system volume information",
    ".appledouble", ".trashes", ".spotlight-v100", ".fseventsd",
    "_duplikaty_katalogator", "odłożone",  # odłożone pliki (duplikaty, podobne, śmieci) nie wracają do skanu
}

ZDJECIE, FILM, MUZYKA_, TOWARZYSZACY, INNE = "zdjecie", "film", "muzyka", "towarzyszacy", "inne"


def rodzaj(nazwa: str) -> str:
    ext = PurePath(nazwa).suffix.lower()
    if ext in ZDJECIA:
        return ZDJECIE
    if ext in FILMY:
        return FILM
    if ext in MUZYKA:
        return MUZYKA_
    if ext in TOWARZYSZACE:
        return TOWARZYSZACY
    return INNE


def pominac_folder(nazwa: str) -> bool:
    n = nazwa.lower()
    return n in SMIECI_FOLDERY or n.startswith(".")


def pominac_plik(nazwa: str) -> bool:
    n = nazwa.lower()
    # .katalogator-tmp(.json): przerwana kopia dużego pliku czekająca na wznowienie
    return n in SMIECI_PLIKI or n.startswith(".") or n.startswith("~$") or ".katalogator-tmp" in n
