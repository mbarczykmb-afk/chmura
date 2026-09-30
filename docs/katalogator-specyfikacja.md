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
  przeniesienie do `Dokumenty/Dokumenty z <rok>/` (od 1.4), ale **dopiero po przejrzeniu
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

11. **Instalator i aktualizacje** ✅ (1.2) — własna ikona, instalator Inno Setup (bez uprawnień
    administratora, skróty w menu Start i na pulpicie, odinstalowanie usuwa zadania harmonogramu,
    zostawia dane), wydania na GitHubie (tag `v*`), powiadomienie o nowej wersji (najwyżej co 12 h,
    można wyłączyć) i „Pobierz i zainstaluj”
12. **Diagnostyka** ✅ (1.2) — dziennik błędów w pliku (rotowany), wyjątki z wątków i błędy JavaScript
    z okna trafiają do dziennika zamiast okienek; „Zgłoś problem”: raport (wersja, system, ustawienia,
    stan zadań, dziennik prac, błędy) do skopiowania / zapisania / zgłoszenia na GitHubie

13. **Poprawki 1.2.1** ✅ — (a) „database is locked”: tryb WAL, 30 s oczekiwania, krótkie transakcje
    zadań w tle; (b) dokumenty: etap 2 na obrazie ~1000 px — tusz (ciemniejszy od lokalnego tła),
    cienkie kreski, **naprzemienność wierszy** (autokorelacja profilu w 10 pasach, w poziomie i w pionie),
    pokrycie strony; śnieg, niebo, ściany i postacie nie mają powtarzających się wierszy;
    (c) podobne: potwierdzenie podpisem jasności 8×8 i kolorów 4×4, grupy wokół wzorca (bez łańcuchów),
    widok jak w Duplikatach (najlepsze zostaje, reszta „odłożę”, można zostawić kilka, „zostaw wszystkie”),
    dwuklik = duży podgląd
14. **Poprawki 1.2.2** ✅ — nagłówek, kroki i pasek zakładek stoją w miejscu, przewija się tylko lewa
    kolumna i zawartość zakładki; duplikaty wyświetlane po 100 grup („Pokaż kolejne 100 grup”)
15. **Poprawki 1.2.3** ✅ — Podobne: duże karty (ok. 250 px, całe zdjęcie bez przycinania, podgląd 600 px
    zamiast miniatury z EXIF), opis pod nazwą pliku
16. **Duże biblioteki — stabilizator i postęp** ✅ (1.3) — sprawdzone na 50 tys. plików:
    - **pasek bieżącego zadania** zawsze widoczny u góry (każda zakładka): procent, pliki x / y, GB x / y,
      prędkość (MB/s lub pliki/s, z ostatnich ~90 s), czas trwania, **szacowany czas do końca**, bieżący plik,
      „Przerwij”; procent także w tytule okna (pasek zadań Windows), „✓ Gotowe”, gdy skończy się w tle;
    - skan w dwóch etapach (liczenie plików → odczyt metadanych), więc od początku znana jest liczba plików;
      postęp kopiowania i porównywania liczony w bajtach, rusza się także przy jednym dużym filmie;
    - **przerwa w dostępie do dysku sieciowego**: zadanie się wstrzymuje („Utracono dostęp do … — czekam”),
      sprawdza co 5 s i po powrocie dysku ponawia ten sam plik (do 15 min, potem zatrzymuje się z zapisanym
      postępem); foldery, których nie dało się odczytać, nie są uznawane za usunięte; pliki z błędem odczytu
      są czytane ponownie przy następnym skanie/analizie;
    - komputer nie usypia się w trakcie zadania (Windows); zamknięcie/zawieszenie okna nie przerywa zadania,
      a ponowne kliknięcie ikony otwiera okno już działającego programu (jedna kopia programu);
    - wydajność: podsumowania nie są przeliczane w trakcie zadań, okno nie wysyła kolejnego zapytania, zanim
      nie dostanie odpowiedzi; podobne zdjęcia liczone raz (z pamięcią), z ograniczeniem porównań dla długich
      serii niemal identycznych ujęć — analiza 40 tys. zdjęć ~10× szybsza, okno odpowiada w < 0,5 s
17. **Poprawki 1.3.1** ✅ — Dokumenty: duże karty jak w Podobnych (całe zdjęcie, podgląd 600 px, dwuklik =
    powiększenie), po 100 na stronie (nieprzejrzane najpierw, zapisywane są decyzje tylko dla wyświetlonych),
    zaznaczanie bez przerysowania listy; naprawione zgniatanie kart w siatkach przy zamrożonym układzie;
    podsumowania dużego projektu liczone w tle — okno pokazuje się od razu („Wczytuję wyniki projektu…”)
18. **Poprawki 1.3.2** ✅ — stały rozmiar kart (240 px, całe zdjęcie 4:3, jak w porównywarce) w Drzewie,
    Dokumentach i Podobnych — bez rozciągania do szerokości okna; w Drzewie większy podgląd i dwuklik = powiększenie
19. **Kategorie, dokumenty, GPS** ✅ (1.4):
    - zakładka **Drzewo** ostatnia i wyróżniona (to wynik całej pracy);
    - **Dokumenty** sortowane po latach, bez dalszych podfolderów: `Dokumenty/Dokumenty z 2023/`
      (bez daty: `Dokumenty/Bez daty`); niezaznaczone kandydaty zostają zwykłymi zdjęciami;
    - **Odłożone**: `Odłożone/Duplikaty`, `Odłożone/Podobne`, `Odłożone/Nieostre` (w folderze źródłowym,
      z cofaniem) i `Odłożone/Śmieci` (w bibliotece); folder „Odłożone” jest pomijany przy skanie;
    - **Śmieci** automatycznie: puste pliki, ikony/kursory, pliki tymczasowe i niedokończone pobrania, skróty,
      miniatury i pamięć podręczna, obrazki ≤ 256 px bez danych aparatu (nigdy zdjęcie z EXIF aparatu/GPS);
    - **Nie z aparatu** — nowa zakładka: grafiki PNG/GIF/WebP/BMP, zrzuty ekranu, pliki z „Pobrane”/internetu,
      małe obrazy i obrazy bez danych aparatu i daty; dla każdego wybór 📷 zdjęcie / 📄 dokument / 🗑 śmieci;
      bez decyzji zostają zdjęciami „do sprawdzenia”; decyzje przekładają plan (z cofaniem);
      filtry w drzewie: Dokumenty, Nie z aparatu, Śmieci; folder przychodzący zostawia takie pliki do przejrzenia;
    - **wykrywanie dokumentów od nowa**: etap 1 szuka *kartki* (największy jasny, bezbarwny, zwarty obszar —
      także na ciemnym stole i w cieniu) z drobną teksturą; etap 2 na kartce: ilość tuszu, **drobne znaki**
      (krótkie odcinki w obu kierunkach — litery, nie ciągłe linie, okna czy kratki) i **wiersze**; na zestawie
      testowym 24/24 dokumentów, 0/29 fałszywych (kratki wentylacyjne, żaluzje, okna, śnieg, liście, tłum, banery);
      stare oceny przeliczane automatycznie przy następnej analizie (decyzje zostają);
    - **GPS**: odporny odczyt współrzędnych (zapis (st, min), same stopnie, 0/0), GPS i data z **XMP** w pliku
      (Lightroom, Photoshop, drony — bez dodatkowego czytania z dysku), z plików **.json Google Zdjęć (Takeout)**
      i **.xmp** obok zdjęcia (json idzie w drzewie razem ze zdjęciem); zdjęcia bez GPS: dopasowanie do wyjazdu
      (±6 h), potem **miejsce z nazwy folderu** („2004 Zakopane”, „Wakacje Hel”, „Chorwacja 2019”, także bez
      polskich liter), potem „w domu”; po aktualizacji pierwszy skan czyta nagłówki ponownie
20. **Decyzja 📷 / 📄 / 🗑 wszędzie** ✅ (1.4.1) — te same trzy przyciski (zdjęcie / dokument / śmieci) w Duplikatach
    (dla całej grupy), Podobnych (dla każdego zdjęcia) — zapis od razu i przełożenie w drzewie, ponowny klik cofa
    decyzję — oraz w Dokumentach (zamiast ptaszka; propozycja programu wstępnie wybrana, „Zapisz decyzje”)
21. **Audyt 1.4.2** ✅ — naprawione „database is locked” przy pierwszym otwarciu nowego projektu (okno i skan
    przełączały bazę na WAL w tej samej chwili; test odtwarzający), decyzje kategorii działają też na planach sprzed 1.4,
    README zaktualizowane; pełny przebieg na 50 tys. plików: skan 46 s, duplikaty 12 s, analiza 133 s, plan 6 s,
    porządkowanie 53 s, okno odpowiada < 0,6 s
22. **Przeglądarka biblioteki i telefon** ✅ (1.5):
    - przycisk **📚 Biblioteka**: *oś czasu* (lata → miesiące → siatka, podgląd na cały ekran ze strzałkami /
      przesuwaniem palcem, filmy odtwarzane) i *mapa* OpenStreetMap (Leaflet 1.9.4 + MarkerCluster dołączone do
      programu): pinezki w miejscach z GPS, grupowanie bliskich, **klik = miniaturka z nazwą, datą i miejscem,
      dwuklik = całe zdjęcie**; zakres: biblioteka (miejsce docelowe) albo wszystko w projekcie;
    - uporządkowane pliki trafiają do bazy od razu (z datą, GPS, aparatem źródła) — biblioteka bez ponownego skanu;
      cofnięcie porządkowania je usuwa;
    - **📱 Na telefon**: osobny serwer tylko do odczytu (sieć domowa / Tailscale), kod QR + 6-cyfrowy PIN,
      blokada po 8 złych próbach (5 min), dostęp tylko do plików z bazy w wybranym zakresie, pliki interfejsu tylko
      z katalogu `ui`; wyłączany jednym przyciskiem; strona dopasowana do telefonu;
    - **24/7 na Raspberry Pi**: `python -m katalogator galeria --folder … --pin …` (skan co 6 h, miniatury na dysku
      Pi) i skrypt `serwer/instaluj-rpi.sh` (dysk SMB tylko do odczytu z automatycznym doborem wersji SMB, usługa
      systemd, Tailscale z podsiecią, najnowsze wydanie z GitHuba; ponowne uruchomienie = aktualizacja)
23. **Audyt interfejsu 1.5.1** ✅ — zakładki w jednym rzędzie (węższa lewa kolumna poniżej 1300 px, przewijanie
    tylko w bardzo wąskim oknie), brak wychodzenia treści poza okno < 900 px, zawijany wiersz harmonogramu,
    „Brak duplikatów” zamiast „Jeszcze nie szukano”, nazwa folderu zamiast pełnej ścieżki w Drzewie, postęp zadania
    tylko na pasku u góry, okno programu otwierane na cały ekran
24. **Wygoda pracy** ✅ (1.6):
    - **przewodnik**: sekcje lewej kolumny zwijane do jednej linijki ze streszczeniem („✓ Zeskanowano 50 000 plików”,
      „✓ 5 915 zbędnych kopii · 27 MB”…); otwarta jest sekcja bieżącego kroku (wyróżniona), reszta na kliknięcie;
      kroki u góry otwierają swoje sekcje; puste zakładki mają własne przyciski („Szukaj duplikatów”, „Analizuj”);
    - **klawiatura** w Dokumentach, Podobnych i „Nie z aparatu”: strzałki = wybór zdjęcia (także w powiększeniu),
      1/2/3 = zdjęcie/dokument/śmieci i od razu następne, spacja = powiększ, Esc = zamknij, Z = zostaw/odłóż (Podobne);
      ściągawka nad zdjęciami;
    - **„↶ Cofnij” w komunikacie** po każdej decyzji (kategorie, zapis zbiorczy, odłożenie kopii, zmiany w Drzewie);
    - **nazewnictwo**: „Pomiń / Nie pomijaj” (zamiast Wyklucz / Przywróć), „Odłóż” = do folderu Odłożone;
      podpowiedzi przy przyciskach; polska odmiana w komunikatach;
    - **ekran powitalny** (4 kroki + słowniczek), raz przy pierwszym uruchomieniu, potem z menu „? → Jak zacząć”
25. **Audyt 1.6.1 — bezpieczeństwo danych** ✅:
    - „przenieś”, gdy źródło i cel to ten sam folder pod dwiema nazwami (np. `Z:\Biblioteka` i
      `\\192.168.100.28\Public\Biblioteka`): wcześniej jedyna kopia mogła zostać usunięta — teraz rozpoznawane
      (ten sam plik) i nic nie jest ruszane; to samo w Duplikatach;
    - sprzątanie pustych folderów po przeniesieniu usuwa tylko znane śmieci systemowe (Thumbs.db, desktop.ini,
      .DS_Store, .wdmc, @eaDir…) — nigdy folderów ukrytych, „Odłożone” ani nieznanych plików — i nigdy nie
      wychodzi ponad wybrane foldery (wcześniej po przeniesieniu wszystkiego granica „znikała”);
    - skan nie wymaga istnienia miejsca docelowego (nowy folder powstanie przy porządkowaniu);
    - galeria „biblioteka” bez wybranego miejsca docelowego jest pusta (nie pokazuje źródeł);
    - kopia w bibliotece nie trafia do „Podobnych” w parze z oryginałem; decyzje po porządkowaniu znów
      natychmiastowe (podobne liczone od nowa tylko, gdy zmienią się przeanalizowane zdjęcia);
    - testy odtwarzające każdy z przypadków (stara wersja je oblewa)
26. **Duże kolekcje i ogromne pliki 1.6.2** ✅ (sprawdzone na 200 tys. plików i filmach 400 GB):
    - **kopia dużego pliku (od 256 MB) wznawiana** po zerwaniu sieci, „Przerwij” lub zamknięciu programu — od
      ostatniego zapisanego kawałka (64 MB), a nie od zera; obok zostaje `nazwa.katalogator-tmp` + `.json`
      (źródło, rozmiar, data, sumy kawałków). Sprawdzenie kopii porównuje każdy kawałek z sumą policzoną ze
      źródła, więc obejmuje też część sprzed przerwy; zmieniony oryginał lub uszkodzona kopia = kopiowanie od nowa.
      Niedokończone kopie nie trafiają do skanu, a osierocone (plik pominięty w planie) są sprzątane;
    - **FAT32** w miejscu docelowym: ostrzeżenie przed porządkowaniem i czytelny błąd dla plików > 4 GB (bez
      wielogodzinnej próby);
    - **pasek i czas do końca** uwzględniają sprawdzanie kopii (drugi odczyt) — wcześniej czas był zaniżony ok. 2×;
      przy > 50 GB okno porządkowania podaje szacunek (≈ 20 MB/s efektywnie przy 40 MB/s sieci);
    - **podobne zdjęcia**: odcisk dzielony na prog+2 pasma, porównywane są odciski ze wspólną *parą* pasm
      (dwa odciski różniące się o ≤ 8 bitów zawsze mają ≥ 2 identyczne pasma, więc nic nie umyka) — 200 tys.
      zdjęć: 23 s zamiast 110 s;
    - **szybkie widoki przy 200 tys. plików**: indeks odcisków i pamiętana lista grup duplikatów (kolejne strony
      0,14 s zamiast 3,5 s), „Nie z aparatu” bez wczytywania wymiarów wszystkich zdjęć, decyzja 1/2/3 przelicza
      tylko pliki z decyzją;
    - pomiar 200 tys. plików (lokalny dysk): skan 148 s, duplikaty 51 s, analiza 512 s, propozycja 24 s,
      kopiowanie 292 s; pamięć do ok. 1 GB; okno odpowiada przez cały czas (stan < 0,2 s)
27. **Nowy wygląd i motywy 1.7** ✅:
    - **przełącznik motywu** jasny / ciemny w nagłówku (☀/☾), zapamiętywany; *? → Motyw jak w systemie Windows*;
      domyślnie ciemny; raport i biblioteka w ramkach przejmują motyw;
    - wygląd w stylu grafiki startowej: granat z niebieską i fioletową poświatą, szklany nagłówek i pasek zadania,
      gradientowe przyciski główne, zaokrąglone karty, wyraźne stany najechania i fokusu, cienkie paski przewijania;
    - **ekran startowy** z grafiką Katalogatora (znika po wczytaniu danych, kliknięcie = pomiń) i ta sama grafika
      w oknie powitalnym;
    - **decyzje widać od razu**: 📷/📄/🗑 w Dokumentach i „Nie z aparatu” zapisują się po kliknięciu (jak w
      Duplikatach i Podobnych); zdjęcie z decyzją szarzeje i dostaje plakietkę „✓ 📄 Dokument” / „✓ 📷 Zdjęcie” /
      „✓ 🗑 Śmieci”; propozycja programu ma przerywaną ramkę (to jeszcze nie decyzja); u dołu „Przejrzane: X z Y
      · zostało Z”; komunikat mówi, gdzie plik trafi, z przyciskiem *Cofnij*; przyciski zbiorcze działają tylko
      na zdjęcia jeszcze bez decyzji
28. **Kopiuj → Przenieś po fakcie 1.7.1** ✅:
    - przełączenie K/P przy folderze od razu zmienia tryb w istniejącej propozycji (poprawki w Drzewie zostają);
    - pliki już skopiowane: nowa propozycja rozpoznaje je w bibliotece (stan „już jest”, kolumna `plan.jest`),
      a porządkowanie w trybie „przenieś” usuwa ich oryginały — każdy dopiero po porównaniu zawartości z kopią;
      kopia zmieniona/usunięta = oryginał zostaje (błąd przy pliku); okno porządkowania ma pole „Usuń N
      oryginałów, które już są w bibliotece”; *Cofnij porządkowanie* przywraca oryginały;
    - Biblioteka: kafelki osi czasu nie są już spłaszczane do pasków (rzędy siatki o wysokości treści)
    - 1.7.2: samo przełączenie K → P po kopiowaniu wystarcza (bez nowej propozycji) — skopiowane pliki dostają
      stan „już jest” z miejscem kopii z dziennika wykonania; „Uporządkuj pliki…” jest aktywne także, gdy zostały
      tylko oryginały do usunięcia (wcześniej przycisk był wyłączony — „nic się nie działo”); podsumowanie
      propozycji pokazuje „Oryginały do usunięcia”; kafelki galerii na starszych telefonach (bez aspect-ratio)
29. **Wykres na osi czasu i Przeglądarka dysków 1.8** ✅:
    - **wykres słupkowy** nad osią czasu (Biblioteka i Przeglądarka): słupek = liczba zdjęć i filmów w miesiącu,
      ciągła oś lat (puste miesiące widać jako przerwy), podpisy lat pod wykresem (klik = cały rok), klik w słupek
      = ten miesiąc, dymek z liczbą po najechaniu / fokusie, wybrany rok wyróżniony, wybrany miesiąc z obwódką;
      skala liniowa od zera, „najwięcej: N w miesiącu”; na telefonie niższy i przewijany w poziomie;
    - **🔭 Przeglądarka** (przycisk w nagłówku): dowolne dyski i foldery (okno wyboru: dyski → podfoldery) są tylko
      skanowane — nic nie jest zmieniane — do osobnej bazy (`%LOCALAPPDATA%\Katalogator\przegladarka\`),
      niezależnej od projektów; oś czasu z wykresem, mapa, podgląd, „Na telefon”; postęp i czas do końca,
      *Przerwij*, zdjęcia pojawiają się już w trakcie skanu; usunięcie folderu z listy chowa jego zdjęcia
    - 1.8.1: **powiększanie w podglądzie** — kółko myszy (do kursora, do 800%), dwuklik = 250%, szczypanie na
      telefonie, przeciąganie powiększonego, + / − / 0, Esc = 100%; to samo w podglądzie Dokumentów i Podobnych;
      Przeglądarka całych dysków pomija foldery systemu i programów (Windows, Program Files, AppData…) i drobne
      obrazki bez daty z aparatu (ikony); małe miniatury siatki zapamiętywane na dysku (szybkie przewijanie przez sieć)
30. **Przeglądarka pro 1.9** ✅ (Biblioteka i Przeglądarka):
    - **wyszukiwarka** w nagłówku: miejscowość („Hel” — zdjęcia, których najbliższa miejscowość to Hel), kraj lub
      znane miejsce za granicą („Włochy”, „Rzym”, „Polska”), rok, miesiąc („lipiec”, „lipca 2019”, „2019-07”),
      fragment nazwy pliku/folderu, aparat — można łączyć („Hel 2019”); wyniki w siatce, *▶ Pokaz slajdów*,
      *＋ Zapisz jako album*;
    - **filmy**: klatka z filmu jako miniatura (wyciągana w oknie, zapamiętywana w bazie), czas trwania na kafelku;
      film, którego przeglądarka nie odtworzy (HEVC z iPhone'a, AVI…) — komunikat i *⤢ Otwórz w programie Windows*
      (na telefonie: *Pobierz film*);
    - **⭐ Kolekcje**: ulubione (☆ w podglądzie albo F) i albumy (*＋ Album* w podglądzie, nowy album, zmiana
      nazwy, usuwanie — zdjęcia zostają na dysku), zapis w bazie oglądanej galerii; na telefonie tylko oglądanie;
      **pokaz slajdów** na pełnym ekranie (▶ / P, 4 s na zdjęcie, film gra do końca, Esc kończy);
    - **mapa → oś czasu**: *📅 Oś czasu tego obszaru* — wykres i siatka tylko ze zdjęć z widocznego fragmentu
      mapy; **„Tego dnia lata temu”** — przycisk nad osią czasu, gdy są zdjęcia z dzisiejszej daty z lat ubiegłych;
    - **samoczynne odświeżanie** Przeglądarki: przy starcie programu i co 6 h wczytuje nowe i zmienione pliki
      (pole *odświeżaj samo co 6 h*, domyślnie włączone)
31. **Stabilny start 1.9.1** ✅: instalator instaluje wersję „folder” (Katalogator.exe + `_internal`), a nie
    jednoplikowy exe — program nie rozpakowuje się już przy każdym starcie do `%TEMP%\_MEI…`, więc znika błąd
    „Failed to load Python DLL … python312.dll” (antywirus/sprzątanie Temp usuwały świeżo rozpakowaną bibliotekę);
    start jest szybszy. Aktualizacja usuwa stare `_internal` przed wgraniem nowych. Jednoplikowy `Katalogator.exe`
    zostaje jako wersja przenośna. CI sprawdza start obu wersji i zainstalowanego programu.
32. **Zestawy dysków w Przeglądarce 1.9.2** ✅: kilka „projektów” Przeglądarki (np. Rodzina, Praca, Stary
    laptop) — każdy z własną listą dysków/folderów; wybór z listy na pasku (＋ nowy, ✎ nazwa, 🗑 usuń — dyski
    i zdjęcia zostają); oś czasu, mapa, szukanie i „tego dnia” pokazują aktywny zestaw; jedna wspólna baza (dysk
    w dwóch zestawach skanuje się raz), ulubione i albumy wspólne; samoczynne odświeżanie obejmuje dyski
    wszystkich zestawów; dotychczasowa lista przechodzi do zestawu „Moje dyski”
33. **Audyt 1.9.3 — Przeglądarka i Katalogator razem** ✅:
    - osobne bazy (projekt / Przeglądarka) — brak wzajemnych blokad; test: Przeglądarka skanuje 6× w trakcie
      przenoszenia 3000 zdjęć przez Katalogator — 0 błędów, zawartość identyczna, po odświeżeniu komplet;
    - ulubione i albumy pamiętają nazwę|rozmiar|datę — po przeniesieniu (Katalogator, Odłożone, ręcznie)
      odnajdują zdjęcia w nowym miejscu;
    - samoczynne odświeżanie Przeglądarki nie rusza w trakcie zadań Katalogatora (ten sam dysk), a po
      porządkowaniu / odłożeniu / cofnięciu odświeża się sama; w pasku informacja, gdy Katalogator pracuje;
    - plik chwilowo otwarty (WinError 32/33: film w Przeglądarce, antywirus) — porządkowanie czeka i ponawia;
    - „Otwórz w programie” tylko dla zdjęć i filmów; miniatury na dysku do ~1,5 GB (najdawniej używane usuwane)

Dane miejscowości: © GeoNames (https://www.geonames.org), licencja CC BY 4.0 —
plik `katalogator/dane/miejsca.tsv.gz` budowany skryptem `narzedzia/zbuduj_miejsca.py`.
