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

## Wygląd (1.51.0)

- Menu **＋ Nowe**: wczytanie pliku Timeline (okno z przeciąganiem), odświeżenie danych, wycieczka ITAKA.
- **Oś czasu** (`os-czasu.js`) i **mapa państw** (`kraje.js`, granice `kraje.json` z Natural Earth — domena publiczna; państwo wyprawy
  z jej miejsc, bez lotnisk).
- **Ślad GPS** (`trasa.js`): linia ciągła tam, gdzie jest ślad; przerywana tam, gdzie Google zapisał tylko początek i koniec
  odcinka. „Wyznacz drogi” pyta `routing.openstreetmap.de` (tylko współrzędne końców luki, po zgodzie; wynik w `localStorage`).

## Szata graficzna (1.53.1)

Podróże używają tej samej szaty co reszta programu („ciemnia”): grafit zamiast granatu, fioletowy akcent, neon tylko przy stanie
aktywnym w ciemnym motywie, ikony liniowe (`/ui/ikony.js` + `ikony-podroze.js` zamieniają emoji na początku przycisków i nagłówków),
czcionka Instrument Sans, jasny i ciemny motyw. Klasy Tailwind (`slate`, `teal`, `emerald`…) czytają kolory ze zmiennych `--p-*`
(`paleta.css`, generowane przez `narzedzia/podroze-css/paleta.js`), więc motyw przełącza się bez zmiany znaczników. Warstwa
`szata.css` ustawia promienie, cienie i okna Leaflet. Przebudowa: `cd narzedzia/podroze-css && npm i tailwindcss@3.4.17 &&
node paleta.js > ../../katalogator/ui/podroze/paleta.css && npx tailwindcss -c tailwind.config.js -i wejscie.css -o ../../katalogator/ui/podroze/podroze.css --minify`.
