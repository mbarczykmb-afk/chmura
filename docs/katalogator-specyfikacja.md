# Katalogator — specyfikacja

Program porządkujący zdjęcia, filmy, muzykę i pozostałe pliki
z dysku sieciowego (WD My Cloud, później nowy NAS). Działa na PC z Windows,
bez internetu (żadne dane ani współrzędne nie wychodzą na zewnątrz).

## Zasada nadrzędna

**Skan → propozycja drzewa → Twoja edycja → dopiero wtedy operacja na plikach.**
Program niczego nie przenosi ani nie kopiuje bez zatwierdzenia planu.

## Przebieg

1. **Wskazanie źródła** (jeden lub kilka folderów) i **miejsca docelowego**.
2. **Skan** źródła i miejsca docelowego (czytane są tylko nagłówki plików:
   EXIF, metadane filmów, tagi muzyki; pełna zawartość tylko przy
   sprawdzaniu duplikatów o identycznym rozmiarze). Skan można przerwać
   i wznowić — wyniki trzymane są w lokalnej bazie.
3. **Raport**: ile plików każdego rodzaju, ile ma datę/GPS, duplikaty, śmieci.
4. **Propozycja drzewa wynikowego** = to, co już jest w miejscu docelowym
   + proponowane nowe foldery i pliki.
5. **Edycja drzewa** w przeglądarce (lokalnie).
6. **Wykonanie**: kopiowanie / przenoszenie / scalanie — **do wyboru**.
7. **Dziennik** i możliwość **cofnięcia** całej operacji.

## Reguły proponowanej struktury

### Zdjęcia (razem ze zrzutami ekranu i obrazami z WhatsApp/Messengera)
```
Zdjęcia/
  Zdjęcia z 2023/
    Marzec w domu/
    Marzec w Olkuszu/
    Lipiec na Helu/
```
- Data: EXIF → nazwa pliku (`IMG_20230714_153012`, `PXL_…`, `IMG-20230714-WA0001`,
  `Screenshot_…`) → data modyfikacji pliku (ostateczność, oznaczona w podglądzie).
- Miejsce: GPS z EXIF → nazwa miejscowości z wbudowanej bazy (offline).
- **Kilka miejsc w miesiącu → osobne foldery.** Seria zdjęć z innej miejscowości
  w kolejnych dniach = osobny folder ("wyjazd").
- **Dom** = najczęstsza lokalizacja → folder „<Miesiąc> w domu”
  (lokalizację domu można poprawić ręcznie).
- **Brak GPS**: dołącz do folderu ze zdjęciami z tego samego dnia, które GPS mają;
  jeśli takich nie ma → „<Miesiąc> w domu”, oznaczone jako „do sprawdzenia”.
- Odmiana nazw: słownik polskich miejscowości w miejscowniku („w Olkuszu”,
  „w Zakopanem”, „na Helu”); gdy brak w słowniku → „Marzec – Olkusz”.
- **Detektor zdjęć dokumentów** (paragony, skany, kartki, dowody): proponuje
  przeniesienie do `Zdjęcia/Dokumenty/`, ale **dopiero po przejrzeniu
  i potwierdzeniu** w osobnym widoku z miniaturami.

### Filmy
Te same reguły co zdjęcia: `Filmy/Filmy z 2023/Marzec w Olkuszu/`.
Filmy bez daty nagrania i GPS (pobrane, kinowe) → `Filmy/Inne/` z zachowaniem
dotychczasowych nazw folderów.

### Muzyka
`Muzyka/<Wykonawca>/<Album>/` wg tagów (albumartist → artist).
Brak tagów → `Muzyka/Nieznany wykonawca/Nieznany album/`.

### Pozostałe pliki
Kopiowane **z zachowaniem dotychczasowych nazw folderów** (np. `Praca/…`).

### Pliki powiązane i śmieci
- Trzymane razem: RAW + JPG, film + napisy (`.srt`), zdjęcie + `.xmp` / `.aae`.
- Pomijane: `.wdmc` (miniatury WD), `Thumbs.db`, `desktop.ini`, `.DS_Store`,
  `@eaDir`, `$RECYCLE.BIN`, `System Volume Information`, pliki i foldery ukryte.

## Edytor drzewa

- Drzewo wynikowe z oznaczeniami: 🟢 nowe, ⚪ już istniejące, 🟡 konflikt/duplikat,
  🔵 do sprawdzenia (np. data z pliku, brak GPS).
- Klik w folder → miniatury zawartości.
- Zmiana nazwy, przeciąganie plików i folderów, scalanie, dzielenie folderu,
  wykluczenie z operacji.
- Cofnij/Ponów; zapis planu i powrót do edycji później.

## Wykonanie

- Tryby: **kopiuj** / **przenieś** / **scal** (do wyboru przy starcie).
- Przenoszenie = kopia → weryfikacja sumy kontrolnej → usunięcie źródła.
- Duplikaty (ta sama zawartość) — nie są kopiowane drugi raz; raport.
- Konflikt nazw przy różnej zawartości → dopisek ` (2)`, nigdy nadpisanie.
- Sprawdzenie wolnego miejsca przed startem; wznawianie po przerwaniu;
  dziennik operacji i cofanie.

## Etapy realizacji

1. **Skaner + raport** ✅ (`katalogator skanuj`, `katalogator raport`)
2. Nazwy miejscowości (offline) + propozycja drzewa + wykrywanie wyjazdów
3. Edytor drzewa w przeglądarce (miniatury, edycja, zapis planu)
4. Detektor zdjęć dokumentów + widok potwierdzania
5. Wykonanie planu (kopiuj/przenieś/scal, weryfikacja, dziennik, cofanie)
