# Podróże — integracja Google Timeline Travels z Katalogatorem

Zakładka **Podróże** uruchamia Twoją aplikację (`C:\Users\Dom\.gemini\antigravity\scratch\google-timeline-travels`)
i pokazuje ją w ramce. Dane podróży **zostają w tym folderze** — nie są częścią repozytorium (jest publiczne).

## Jak to działa (kontrakt)

| Co | Jak |
|---|---|
| Uruchomienie | `node server.js` w folderze projektu, zmienna `PORT` (domyślnie 8080). Jeśli na porcie już ktoś odpowiada (np. `launch_app.bat`), Katalogator go używa i **nie zatrzymuje**. |
| Adres w ramce | `http://127.0.0.1:<port>/?katalogator=1&motyw=dark\|light` |
| Motyw | Katalogator wysyła do ramki `postMessage({typ:"katalogator-motyw", motyw, kolory:{"--kat-bg":…}})` po załadowaniu ramki i przy każdej zmianie motywu. |
| Adapter | `katalogator-motyw.js` + `.css` (+ czcionka Instrument Sans) dopisywane do projektu przyciskiem (Ustawienia → Podróże). Dopisuje do `index.html` **jedną linię** (po znaczniku `<!-- katalogator-motyw -->`), kopia: `index.html.katalogator.bak`. Odinstalowanie przywraca stan sprzed. |
| Zmienne CSS | `--kat-bg --kat-panel --kat-fg --kat-mut --kat-lin --kat-akc --kat-akc-fg --kat-font`; atrybuty na `<html>`: `data-katalogator="1"`, `data-katalogator-motyw="dark\|light"`. |

Adapter celowo nie zmienia tła, kart ani układu aplikacji (nie zna jej klas CSS) — daje czcionkę, pasek przewijania, kolor
akcentu i zmienne. **Dopasowanie wyglądu kart, przycisków i map robi się w CSS samego projektu** — to zadanie dla agenta,
który widzi pliki projektu (patrz niżej).

## Zadanie dla `gemini-worker` (na Twoim komputerze, w folderze projektu)

> Dopasuj wygląd aplikacji Google Timeline Travels do stylu Katalogatora, gdy jest otwarta w jego ramce
> (`html[data-katalogator]`). Nie zmieniaj działania ani danych — tylko CSS (nowy plik `katalogator-styl.css`, dołączony
> w `index.html` po `katalogator-motyw.css`), a poza ramką (bez `data-katalogator`) wygląd ma zostać taki jak dziś.
>
> Styl Katalogatora („ciemnia”): neutralny grafit zamiast granatu (tło `--kat-bg`, panele `--kat-panel`), jedna czcionka
> `--kat-font` (Instrument Sans), zdjęcia i mapa jako bohaterowie — karty bez ramek i cieni, podpisy ciche (`--kat-mut`),
> kolor tylko dla stanu aktywnego/zaznaczonego (`--kat-akc`, fiolet; neon turkus→fiolet→róż tylko w ciemnym motywie, tam
> też poświata), przyciski bez obwódek (tło dopiero po najechaniu), promienie 8–10 px, ikony liniowe zamiast emoji,
> fokus z klawiatury widoczny, `prefers-reduced-motion` respektowane. Kontrast tekstu ≥ 4,5:1 w obu motywach.
> Zmienne `--kat-*` są ustawiane przez adapter; ich wartości dla motywu jasnego i ciemnego są w `katalogator-motyw.css`.
> Zrób zrzuty (Playwright) widoku katalogu, mapy, szczegółów wyprawy i profilu wysokości w obu motywach, w ramce 1400×900.

## Zadanie dla `codex-worker` (przegląd i testy po stronie projektu)

> Przejrzyj projekt pod kątem: (1) czy `server.js` czyta port z `process.env.PORT` i nasłuchuje tylko na `127.0.0.1`,
> (2) czy nie ustawia nagłówków blokujących ramki (`X-Frame-Options`, `frame-ancestors`) dla `http://127.0.0.1:*`,
> (3) czy `sw.js` nie cache'uje w sposób, który przytrzymuje starą wersję po aktualizacji, (4) czy jakikolwiek plik z tokenami
> (Strava, Intervals) nie trafia do `git`/backupów. Dopisz testy (np. Node `--test`) dla generowania wypraw z
> `generate_all_real_trips.py` na małej próbce danych.

## Pięć propozycji ulepszeń

1. **Zdjęcia z biblioteki Katalogatora zamiast własnego skanowania.** Katalogator ma już datę, GPS i miniatury każdego
   zdjęcia (oś czasu, mapa, „Tego dnia”). Zdjęcia dnia wyprawy można brać z jego API (zakres dat + obszar) — odpada
   `auto_index_all_trip_photos.py`, folder `thumbnails/` i zależność od litery dysku `U:\`.
2. **Prywatność i bezpieczeństwo.** `Os_czasu_real.json` (95 MB, cała historia lokalizacji) i tunel `cloudflared`
   wystawiają wrażliwe dane: dostęp tylko z kluczem (jak most do domu w Katalogatorze), tryb „udostępnij wyprawę” z
   rozmyciem okolic domu (np. 500 m), tokeny Strava/Intervals w `.env` poza folderem objętym backupem/synchronizacją.
3. **Jedno źródło danych zamiast dwóch kopii.** `sample-trips.json` (25 MB) i `sample-data.js` (23,5 MB) to to samo —
   zamiast tego SQLite z ładowaniem wypraw na żądanie (lista lekka, trasa GPS dopiero po wejściu) i przyrostowa aktualizacja
   przyciskiem „Zaktualizuj podróże” (nowe dni z Timeline + Strava) bez przeliczania wszystkiego.
4. **Wyprawa ↔ album ↔ osoby.** Z wyprawy jednym kliknięciem tworzysz album „Madera 2024” w Katalogatorze (zdjęcia z jej dni),
   widzisz, kto jest na zdjęciach (Osoby), a w Katalogatorze w „Tego dnia” pojawia się znacznik wyprawy. Plus podsumowania:
   rok w liczbach (km, przewyższenia, szczyty, kraje), wejścia na szczyty z PeakBagger na osi czasu.
5. **Szybkość i tryb offline.** Dane podróży wczytywane naraz (23 MB) spowalniają start — podział na pliki per wyprawa,
   uproszczenie tras (Douglas–Peucker po stronie generatora), cache kafli mapy (OSM/Topo) w Service Workerze dla ostatnio
   oglądanych obszarów, profil wysokości liczony z wygładzonych danych barometrycznych (mniej „ząbków”).
