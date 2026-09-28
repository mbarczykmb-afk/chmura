# Katalogator — specyfikacja

Program porządkujący zdjęcia, filmy, muzykę i pozostałe pliki
z dysku sieciowego (WD My Cloud, później nowy NAS). Działa na PC z Windows,
bez internetu (żadne dane ani współrzędne nie wychodzą na zewnątrz).

## Zasada nadrzędna

**Skan → propozycja drzewa → Twoja edycja → dopiero wtedy operacja na plikach.**
Program niczego nie przenosi ani nie kopiuje bez zatwierdzenia planu.

## Przebieg

1. **Wskazanie źródła** (jeden lub kilka folderów) i **miejsca docelowego** —
   drzewo jak w commanderze: podpięte dyski (także sieciowe), rozwijanie,
   dwa ptaszki przy każdym folderze: **K — kopiuj** (oryginały zostają) lub
   **P — przenieś** (oryginały usuwane ze źródła po weryfikacji kopii);
   folder obejmuje podfoldery; cel wybierany
   w tym samym drzewie, z możliwością utworzenia nowego folderu.
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

- Tryb **kopiuj** / **przenieś** — ustawiany osobno dla każdego wybranego folderu
  (ptaszki K/P w drzewie); **scalanie** z istniejącą zawartością celu wynika z drzewa.
- Przenoszenie = kopia → weryfikacja sumy kontrolnej → usunięcie źródła.
- Duplikaty (ta sama zawartość) — nie są kopiowane drugi raz; raport.
- Konflikt nazw przy różnej zawartości → dopisek ` (2)`, nigdy nadpisanie.
- Sprawdzenie wolnego miejsca przed startem; wznawianie po przerwaniu;
  dziennik operacji i cofanie.

## Etapy realizacji

1. **Skaner + raport** ✅ — aplikacja okienkowa `Katalogator.exe`, drzewo folderów z ptaszkami K/P
1a. **Detektor duplikatów** ✅ — porównanie zawartości (rozmiar → 1 MB początek/koniec →
    pełny odcisk BLAKE2b), wybór pliku, który zostaje, odłożenie kopii do
    `_Duplikaty_Katalogator` (bez kasowania) i cofanie
2. **Propozycja drzewa** ✅ — nazwy miejscowości offline (GeoNames, dzielnice → miasto,
   zagranica → kraj), polski miejscownik (reguły + wyjątki), dom = najczęstsze miejsce,
   wyjazdy (seria zdjęć poza domem, przerwa ≤ 48 h, etykieta = najczęstsze miejsce wyjazdu),
   zdjęcia bez GPS dopasowane do wyjazdu (±6 h) lub „w domu”, filmy z telefonu jak zdjęcia,
   pozostałe filmy → `Filmy/Inne`, muzyka `Wykonawca/Album`, pliki towarzyszące
   (XMP, RAW, napisy) idą za plikiem głównym, pliki już obecne w celu i duplikaty pomijane
3. **Edytor drzewa** ✅ — drzewo wynikowe z licznikami (nowe / już są / do sprawdzenia /
   kolizje / pominięte), miniatury, zmiana nazwy (scalanie), przenoszenie folderów i plików
   (także przeciąganiem), nowy folder z zaznaczonych, wykluczanie, cofnij/ponów (Ctrl+Z/Y),
   plan zapisany w bazie
4. **Detektor zdjęć dokumentów** ✅ — ocena na miniaturze EXIF (jasne tło, mało koloru,
   tusz, krawędzie tekstu); widok do przejrzenia, potwierdzone → `Zdjęcia/Dokumenty`
5. **Wykonanie planu** ✅ — kopiuj/przenieś wg ptaszków, kopia do pliku tymczasowego +
   weryfikacja sumą kontrolną, szybka zmiana nazwy na tym samym dysku, brak nadpisywania
   („ (2)”), kontrola wolnego miejsca, wznawianie, usuwanie pustych folderów źródłowych,
   dziennik i cofanie
6. **Podobne i nieostre zdjęcia** ✅ — odcisk obrazu (dHash 64 bity, pasma LSH, próg 5 bitów),
   najlepsze w grupie = największa rozdzielczość i ostrość; lista najmniej ostrych;
   odkładanie do `_Duplikaty_Katalogator` z cofaniem

7. **Projekty** ✅ (1.1) — osobne foldery, skan, propozycja, decyzje i historia dla każdego projektu;
   notatki (zapis automatyczny), dziennik prac, oznaczanie folderów jako przejrzanych
   i „Następny →” do kolejnego nieprzejrzanego; pasek postępu; przełączanie między projektami
8. **Edytor: wyszukiwanie i zmiany zbiorcze** ✅ (1.1) — szukanie po nazwie/folderze/źródle,
   filtry (do sprawdzenia, bez GPS, data z pliku, ta sama nazwa, pominięte, błędy),
   Shift+klik, „Ustaw miejsce…” (np. Hel → „<Miesiąc> na Helu”), „Ustaw datę…” (zmienia
   rok/miesiąc w drzewie, bez modyfikacji pliku) — wszystko z cofaniem
9. **Formaty** ✅ (1.1) — daty/aparat/GPS z RAW (TIFF: DNG, CR2, NEF, ARW, ORF, RW2, PEF, SRW;
   RAF przez wbudowany JPEG; CR3 jak MP4), daty z AVI (IDIT/ICRD) i MKV/WebM (DateUTC),
   HEIC (pillow-heif); podgląd klatki filmu w edytorze (przeglądarka czyta tylko fragment pliku),
   dwuklik = odtwarzanie
10. **Folder przychodzący** ✅ (1.1) — nowe pliki przenoszone do biblioteki wg tych samych zasad,
    pliki z niepewną datą zostają do przejrzenia; identyczny plik już obecny w bibliotece nie
    tworzy kopii „(2)”; ustawiane „Mieszkam w”; tryb `Katalogator.exe --auto <projekt>` i zadanie
    w Harmonogramie zadań Windows (codziennie o wybranej godzinie), wynik w dzienniku i auto.log

Dane miejscowości: © GeoNames (https://www.geonames.org), licencja CC BY 4.0 —
plik `katalogator/dane/miejsca.tsv.gz` budowany skryptem `narzedzia/zbuduj_miejsca.py`.
