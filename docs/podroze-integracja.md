# Podróże — Google Timeline Travels jako część Katalogatora

Zakładka **Podróże** to dziennik wypraw (oś czasu Google, trasy GPS, szczyty, rezerwacje, zdjęcia) wbudowany w program.
Nie ma osobnego programu ani Node: serwer Katalogatora serwuje aplikację pod `/podroze/`, a zakładka pokazuje ją w ramce.
Kod aplikacji jest w `katalogator/ui/podroze/`, serwer w `katalogator/podroze.py`.

**Dane podróży nie należą do repozytorium (jest publiczne).** Leżą w folderze danych programu
(`%LOCALAPPDATA%\Katalogator\podroze\dane`) i trafiają tam z dotychczasowego folderu projektu przyciskiem
*Importuj dane* (Ustawienia → Podróże albo sama zakładka). Oryginały zostają nietknięte.

## Kontrakt

| Co | Jak |
|---|---|
| Adres | `/podroze/?t=<token>` — przy pierwszym wejściu serwer ustawia ciasteczko `kat_podroze` (`HttpOnly`, `SameSite=Strict`, `Path=/podroze`) |
| API aplikacji | `api/version`, `api/user-photos`, `api/photo?path=…`, `api/reindex` (POST) |
| Zdjęcia | tylko z folderów biblioteki projektów, folderów Przeglądarki i dodatkowych z ustawień; bez SVG; zdjęcie spoza nich → 403 |
| Dostępność | tylko na komputerze — serwer telefonu i most do domu blokują `/podroze` |
| Motyw | `postMessage({typ:"katalogator-motyw", motyw, kolory:{"--kat-bg":…}})`, aplikacja prosi o niego komunikatem `katalogator-gotowe` |
| Zasoby | wszystko lokalnie (Tailwind zbudowany raz — `narzedzia/podroze-css/`, Leaflet, JSZip, czcionka); z sieci tylko kafelki mapy OSM |

## Pięć propozycji ulepszeń

1. **Zdjęcia z biblioteki Katalogatora zamiast skanowania `U:\`** — data, GPS i miniatury już są w bazie; zdjęcia dnia wyprawy
   brane z niej (zakres dat + obszar). *(Wbudowana wersja już szuka plików po nazwie w bazie Przeglądarki.)*
2. **Prywatność** — dostęp tylko z kluczem, tryb „udostępnij wyprawę” z rozmyciem okolic domu, klucze Strava/Intervals w
   ustawieniach programu, nie w plikach projektu.
3. **Jedno źródło danych** — SQLite zamiast dwóch kopii 25 MB, ładowanie wypraw na żądanie, przyrostowa aktualizacja.
4. **Wyprawa ↔ album ↔ osoby** — album z wyprawy jednym kliknięciem, osoby na zdjęciach, znacznik wyprawy w „Tego dnia”, rok w liczbach.
5. **Szybkość i offline** — pliki per wyprawa, uproszczenie tras, cache kafli mapy, wygładzony profil wysokości.

## Etap 2 (plan)

Port generatora wypraw (`generate_all_real_trips.py`) i integracji Strava / Intervals / PeakBagger / OSM do modułów Pythona
Katalogatora, z paskiem postępu; klucze z ustawień programu; bez zaszytych danych osobistych (rezerwacje, ścieżki).
