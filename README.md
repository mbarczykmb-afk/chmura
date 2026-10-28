# chmura — własna "chmura" na WD My Cloud (Gen1)

## Urządzenie

| | |
|---|---|
| Model | WD My Cloud 3 TB, 1 dysk (P/N `WDBCTL0030HWT-00`) |
| Generacja | **Gen1** (firmware `v04.06.00-111`, "My Cloud OS 3") |
| Sprzęt | ARM 2 rdzenie 650 MHz, 256 MB RAM |
| Zajęte | ok. 700 GB (filmy 310 GB, inne 310 GB, zdjęcia 71 GB) |
| Klienci | PC (Windows), telefon Android |

Wsparcie WD i zdalny dostęp przez mycloud.com zakończyły się 15.04.2022.
Plan: dysk działa **tylko w sieci lokalnej**, a dostęp z zewnątrz zapewnia
własny VPN (nie serwery WD).

---

## Etap 0 — zabezpieczenie (zrób teraz)

1. **Panel dysku → Ustawienia → Ogólne → Dostęp do chmury: WYŁ.**
2. **Router:** usuń wszystkie przekierowania portów (port forwarding) na IP dysku
   i wyłącz UPnP.
3. **Panel → Ustawienia → Sieć → SSH: WYŁ.** (włączymy tylko na czas prac).
4. **Użytkownicy:** każdy z 2 kont z silnym, unikalnym hasłem;
   udziały prywatne zamiast "Publiczny", jeśli nie są potrzebne dla gości.
5. **Stały adres IP** dysku: rezerwacja DHCP w routerze
   (np. `192.168.1.50`) — ułatwia łączenie z PC i telefonu.

## Etap 1 — kopia zapasowa

~700 GB danych, dysk ma już kilka lat. Przed jakimikolwiek zmianami systemu:

- Podłącz dysk USB (≥ 1 TB) do portu USB z tyłu My Cloud
  → **Panel → Kopie zapasowe → Kopie USB** → kopia udziałów na dysk USB,
- albo skopiuj udziały z PC na dysk zewnętrzny.

## Etap 2 — dostęp lokalny (w domu)

**PC (Windows):** automatycznie — `windows/mapuj-dysk.ps1` (instrukcja w pliku). Ręcznie: Eksplorator → *Ten komputer* → *Mapuj dysk sieciowy* →
`\\192.168.1.50\NazwaUdziału` (lub `\\WDMYCLOUD\NazwaUdziału`),
zaznacz *Połącz ponownie przy logowaniu*.

**Android** (aplikacja WD My Cloud już nie działa) — dowolny menedżer plików
z obsługą SMB, np. *Material Files* (open source) lub *CX File Explorer*:
dodaj serwer SMB → host `192.168.1.50`, użytkownik i hasło z dysku.
Filmy: *VLC for Android* → Przeglądaj → Sieć lokalna.

## Etap 3 — dostęp zdalny (poza domem) — później

### Wariant tymczasowy (działa, gdy PC jest włączony) — AKTUALNY

Sieć: światłowód → Huawei HG8245H (ONT operatora, brak dostępu) → TP-Link
AX3000 → dysk + PC. Tailscale omija NAT i nie wymaga otwierania portów.

1. Załóż konto na <https://tailscale.com> (np. logowanie przez Google).
2. **PC:** zainstaluj Tailscale for Windows, zaloguj się. Następnie PowerShell
   jako Administrator: `windows/tailscale-podsiec.ps1`
   (udostępnia sieć domową i wyłącza usypianie PC przy zasilaniu).
3. **Panel Tailscale** (<https://login.tailscale.com/admin/machines>) → przy PC:
   *Edit route settings* → zatwierdź podsieć; *Disable key expiry*.
4. **Android:** aplikacja Tailscale (to samo konto) → włącz; w menedżerze plików
   serwer SMB pod lokalnym IP dysku — działa także na LTE poza domem.

### Wariant docelowy (24/7)

Wymaga czegoś, co działa w domu 24/7. Opcje, od najprostszej:

1. **VPN w routerze** — jeśli router ma serwer WireGuard/OpenVPN
   (np. FRITZ!Box, ASUS, TP-Link Omada/Archer z VPN, MikroTik).
   Telefon i laptop łączą się VPN-em → widzą dysk jak w domu.
2. **Raspberry Pi (lub stary PC) + Tailscale** jako *subnet router*
   dla sieci domowej. Bez otwierania portów w routerze.
3. **Debian na samym My Cloud** (projekt społeczności Fox_exe dla Gen1)
   + Samba + Tailscale/WireGuard + File Browser. Najwięcej pracy i ryzyka;
   tylko po wykonaniu Etapu 1.

**Gotowe: Raspberry Pi 24/7** (opcja 2 + galeria zdjęć na telefon) — patrz niżej
[Biblioteka na telefonie 24/7](#biblioteka-na-telefonie-247-raspberry-pi).

---

## Katalogator — porządkowanie zdjęć, filmów, muzyki i plików

Specyfikacja: [`docs/katalogator-specyfikacja.md`](docs/katalogator-specyfikacja.md).
Wersja 1.4: projekty (praca na kilka dni), skan i raport, duplikaty, analiza zdjęć (dokumenty, podobne, nieostre,
„nie z aparatu”), śmieci, propozycja drzewa („Zdjęcia z 2023 → Marzec w Olkuszu”, „Dokumenty z 2023”), edytor
z wyszukiwarką i zmianami zbiorczymi, porządkowanie z weryfikacją i cofaniem, folder przychodzący z harmonogramem,
stabilna praca na dużych bibliotekach (sprawdzone: 200 tys. plików, filmy 400 GB, przerwy w dostępie do
dysku sieciowego).
Nazwy miejscowości: © GeoNames, CC BY 4.0.

**Instalacja:**
1. Wejdź na <https://github.com/mbarczykmb-afk/chmura/releases> i pobierz najnowszy
   **Katalogator-Setup-X.Y.Z.exe**.
2. Uruchom instalator (bez uprawnień administratora). Windows SmartScreen może ostrzec
   o nieznanym wydawcy → *Więcej informacji* → *Uruchom mimo to*. Instalator tworzy skrót
   w menu Start (i opcjonalnie na pulpicie); program trafia do `%LOCALAPPDATA%\Programs\Katalogator`.
   Wersja przenośna bez instalacji: `Katalogator.exe` z tej samej strony.
   Program sam powiadomi o nowej wersji (*? → Sprawdź aktualizacje*) i zainstaluje ją jednym kliknięciem.
   Jeśli Windows 11 pokaże *„Zasady kontroli aplikacji zablokowały ten plik”* (WinError 4551), to działa
   **Inteligentna kontrola aplikacji** (Smart App Control): blokuje programy bez podpisu cyfrowego, a Katalogator
   go nie ma. Wyłącz ją: *Ustawienia → Prywatność i zabezpieczenia → Zabezpieczenia Windows → Kontrola aplikacji
   i przeglądarki → Ustawienia Inteligentnej kontroli aplikacji → Wyłączone* i uruchom instalator ponownie.

**Praca krok po kroku:**
1. *Co porządkujemy?* — rozwiń dysk (sieciowe mają ikonę 🌐) i przy folderach zaznacz **K** (kopiuj — oryginały
   zostają) albo **P** (przenieś). *Dokąd?* → *Wybierz folder…* → **Skanuj** → raport.
2. **Szukaj duplikatów** → zakładka *Duplikaty* (po 100 grup): w każdej grupie wybierz plik, który zostaje →
   *Odłóż zaznaczone kopie*. Kopie trafiają do `Odłożone\Duplikaty` (nic nie jest kasowane; *Cofnij* przywraca).
3. **Analizuj zdjęcia** → zakładki:
   - *Dokumenty* — zdjęcia kartek, paragonów, skanów: 📷 zdjęcie / 📄 dokument / 🗑 śmieci → *Zapisz decyzje*;
     dokumenty trafią do `Dokumenty\Dokumenty z <rok>`;
   - *Podobne* — seria ujęć, kopie z WhatsAppa: najlepsze zostaje, reszta do `Odłożone\Podobne`;
   - *Nie z aparatu* — grafiki, zrzuty ekranu, obrazki z internetu: zdecyduj, co to jest.
   Przyciski 📷 / 📄 / 🗑 są też w Duplikatach i Podobnych (zapis od razu, ponowny klik cofa).
4. **Utwórz propozycję** → zakładka **🌳 Drzewo** (najważniejsza): popraw nazwy folderów, przeciągaj pliki,
   *Ustaw miejsce…*, *Ustaw datę…*, wykluczaj; filtry (do sprawdzenia, bez GPS, dokumenty, śmieci…); *Cofnij/Ponów*.
   Śmieci (ikony, pliki tymczasowe, puste, skróty) program sam odkłada do `Odłożone\Śmieci`.
5. **Uporządkuj pliki…** — kopiowanie/przenoszenie z weryfikacją każdej kopii; *Cofnij porządkowanie* przywraca stan.
   Pasek u góry pokazuje postęp, prędkość i czas do końca; gdy dysk sieciowy zniknie, program czeka i ponawia.
   **Najpierw skopiowałeś, a teraz chcesz przenieść?** Przełącz folder z **K** na **P** i kliknij *Uporządkuj
   pliki…* — program usunie oryginały, które już są w bibliotece (każdy po porównaniu z kopią; nic nie kopiuje
   drugi raz; *Cofnij porządkowanie* je przywraca).
   Duże pliki (filmy po kilkadziesiąt–kilkaset GB): przerwana kopia rusza dalej od miejsca przerwania, nie od
   zera. Dysk docelowy sformatowany jako FAT32 nie mieści plików > 4 GB — program ostrzeże przed startem.
   Orientacyjnie: każdy plik jest kopiowany i sprawdzany, więc przez sieć z WD My Cloud (~40 MB/s)
   400 GB to ok. 5–6 godzin — najlepiej na noc (komputer nie uśnie w trakcie).
6. **Projekty** (przycisk z nazwą projektu u góry) — osobne foldery, notatki i dziennik; w *Drzewie* oznaczaj
   foldery „✓ Przejrzany” i przechodź dalej przyciskiem *Następny →*.
7. **Nowe pliki** — folder przychodzący (np. zrzuty z telefonu), *Mieszkam w*, *Sprawdź nowe pliki* →
   *Przenieś do biblioteki*; opcjonalnie codziennie o wybranej godzinie (Harmonogram zadań Windows).
**Wygląd:** przycisk ☀/☾ w nagłówku przełącza motyw jasny / ciemny (zapamiętany; *? → Motyw jak w systemie*).
Po kliknięciu 📷/📄/🗑 decyzja zapisuje się od razu — zdjęcie szarzeje i pokazuje „✓ Dokument” itp.
**Wygoda:** sekcje po lewej zwijają się same — otwarta jest ta, którą trzeba teraz zrobić (kliknij nagłówek,
żeby otworzyć inną). W Dokumentach, Podobnych i „Nie z aparatu” działa **klawiatura**: strzałki, **1** zdjęcie,
**2** dokument, **3** śmieci (od razu następne zdjęcie), spacja — powiększenie. Po każdej decyzji na dole pojawia
się komunikat z przyciskiem **↶ Cofnij**. *? → Jak zacząć* pokazuje krótką instrukcję.

8. **Problemy:** *? → Zgłoś problem* — raport diagnostyczny (bez zawartości plików) do skopiowania, zapisania albo
   zgłoszenia na GitHubie. Dziennik błędów: `%LOCALAPPDATA%\Katalogator\logi\katalogator.log`.

Miejsce zdjęć: GPS z EXIF, XMP, plików `.json` Google Zdjęć i `.xmp`; bez GPS — dopasowanie do wyjazdu, nazwa
folderu („2004 Zakopane”), a na końcu „w domu”.

9. **📚 Biblioteka** (przycisk u góry) — przeglądanie uporządkowanej biblioteki:
   - *📅 Oś czasu*: lata → miesiące → zdjęcia; kliknięcie = całe zdjęcie (strzałki ← → / przesunięcie palcem);
   - *🗺 Mapa* (OpenStreetMap): pinezki w miejscach zrobienia zdjęć (z GPS), bliskie łączą się w grupy z liczbą;
     **kliknięcie pinezki = miniaturka**, **dwa kliknięcia = całe zdjęcie**;
   - *📱 Na telefon* (także przycisk 📱 w nagłówku): kod QR + PIN — telefon w tej samej sieci Wi-Fi (albo
     z Tailscale — z każdego miejsca) otwiera **pilota**: co teraz robi komputer (postęp, czas do końca, Przerwij),
     kroki projektu z przyciskiem *Uruchom* (skan, duplikaty, analiza, propozycja, porządkowanie; w Sprzątaniu —
     usuwanie odłożonych, z potwierdzeniem), przełączanie projektów oraz przeglądanie: Biblioteka, cały projekt,
     Przeglądarka dysków. Projekt zakłada się i ustawia na komputerze; *Pozwól sterować z telefonu* można odznaczyć —
     wtedy telefon tylko ogląda. *✎ Ustaw swój PIN* — stały PIN (4–12 cyfr), a telefon zostaje zalogowany
     także po ponownym uruchomieniu programu. Działa, dopóki Katalogator jest otwarty.

**Szybsze przeglądanie list** — w *Dokumentach* i *Nie z aparatu* ułożone pliki chowają się przed wczytaniem
kolejnych (*Schowaj przejrzane i pokaż kolejne*, *↺ pokaż przejrzane*); identyczne kopie są jedną kartą („+2 kopie”) —
decyzja obejmuje wszystkie; w *Podobnych* identyczna kopia jest oznaczona. Foldery dokumentów w drzewie mają w nawiasie
foldery, z których pochodzą: *Dokumenty z 2023 (Faktury, Skany, Pobrane)*. Po odłożeniu / usunięciu plików albo nowym
skanie drzewo tworzy się od nowa przy wejściu w 🌳 Drzewo (gdy masz w nim ręczne poprawki — najpierw pyta).
W podglądzie zdjęcia w Bibliotece i Przeglądarce — **mała mapa** z miejscem zrobienia (klik = duża mapa).

**🖥 Pełny program z telefonu** (gdy Katalogator działa na komputerze): 📱 → kod QR + PIN → na pilocie *🖥 Pełny
program* — wszystkie zakładki (Duplikaty, Dokumenty, Podobne, Drzewo, kosz…) w układzie na telefon. Serwer telefonu
po PIN-ie przekazuje zapytania do programu na komputerze; wymaga *Pozwól sterować z telefonu*; zamknąć programu ani
zainstalować aktualizacji z telefonu się nie da. **Spoza domu**: VPN do domu (WireGuard na domowym serwerze albo
Tailscale) i ten sam adres — program nie jest wystawiany wprost do internetu.

**Podobne — kopie w wielu folderach** (od 1.22): to samo zdjęcie w kilku folderach (kopia zapasowa, zapisane na nowo,
„IMG_1 (1).jpg”) liczy się jako jedno — seria nie wraca osobno dla każdego folderu; kopie mają znacznik „= kopia tego
samego zdjęcia”. ⚡ Hurtem: *1) Odłóż same kopie tych samych zdjęć* (bezpieczne) i *2) We wszystkich grupach zostaw
tylko ★* — oba do cofnięcia. **Nie z aparatu — grupy**: obrazy zebrane wg folderu (pojedyncze razem, wg powodu), cała
grupa zaznaczona; odznaczasz prawdziwe zdjęcia i „✓ Zatwierdź grupę” (zaznaczone → śmieci / dokumenty / zdjęcia).

**1.48.0:** 👤 **Dokładniejsze rozpoznawanie twarzy do wyboru.** W zakładce Ustawienia, w części Przeglądarka, sekcja Osoby, można przełączyć silnik na **InsightFace buffalo_l**, ten sam co w Immich: wykrywanie SCRFD i rozpoznawanie ArcFace. Lepiej znajduje małe, boczne i ciemne twarze i pewniej odróżnia podobne osoby. W teście ta sama osoba w innym ujęciu dała podobieństwo 0,91 (wcześniej 0,66), a dwie różne osoby 0,01 (wcześniej 0,13). Model ma ok. 190 MB i pobiera się raz z oficjalnego wydania InsightFace, ze sprawdzeniem sum kontrolnych. **Imiona i połączenia osób zostają.** Po zmianie silnika zdjęcia są przeglądane od nowa w tle (można przerwać), a nowa twarz przejmuje osobę od starej twarzy w tym samym miejscu zdjęcia. Licencja modeli InsightFace dopuszcza tylko użytek niekomercyjny, więc prywatne zdjęcia rodzinne są w porządku. Standardowy silnik (SFace) zostaje domyślny.

**1.47.0:** 📄 **OCR dokumentów.** Zdjęcia, które przypominają dokumenty, program teraz **czyta** (RapidOCR, modele PaddleOCR PP-OCRv6, w całości na komputerze, z polskimi znakami). Odczytany tekst potwierdza dokument (dużo liter, a więc dokument) albo go wyklucza: żaluzje, kafelki czy pasy, które tylko wyglądają jak wiersze tekstu, nie mają liter. W zakładce Dokumenty pod miniaturą widać początek odczytanego tekstu. **Wyszukiwarka znajduje zdjęcia po tekście z dokumentów** (np. „faktura”, „PESEL”, „Orlen”), także w Przeglądarce. Tekst trafia do wspólnego indeksu, więc ten sam plik nie jest czytany drugi raz w innym projekcie. Czytane są tylko zdjęcia podobne do dokumentów (ok. 1 s na zdjęcie), a przerwane czytanie rusza dalej przy następnej analizie.

**1.46.1:** 🗂 Albumy i ulubione przenoszą się razem z biblioteką na inny dysk (np. My Cloud `Z:` → NAS `U:`). Wcześniej po zamianie folderu w Przeglądarce album wyglądał na pusty, bo jego wpisy wskazywały stary dysk. Teraz program sam odnajduje te zdjęcia w oglądanych folderach po nazwie, rozmiarze i dacie i poprawia ścieżki.

**1.46.0:** ⚙ Nowa zakładka **Ustawienia** u góry, obok Przeglądarki, Porządkowania i Sprzątania. Wszystkie ustawienia są w jednym miejscu i każde można tam zmienić. Zakładka ma cztery części: **Program** (wygląd, start, telefon, most, aktualizacje, kopia zapasowa), **Projekt** (nazwa, notatki, źródła z przełącznikiem K/P, biblioteka, „Mieszkam w”, foldery przychodzące i godzina codziennego sprawdzania), **Przeglądarka** (zestawy dysków i folderów, skanowanie, samoczynne odświeżanie, zapamiętany wygląd: kolejność, rodzaj, wykres, panele) oraz **Porządkowanie i Sprzątanie** (schowany pasek, podpowiedzi, usuwanie duplikatów na stałe, Podobne po jednej grupie, widok „Nie z aparatu”). Spis po lewej przenosi do wybranej części, a F1 pokazuje opis zakładki. Dotychczasowe okno ⚙ otwiera teraz tę zakładkę. Poprawka: ścieżki kończące się `\` (np. `N:\`) wyświetlały się odwrócone jako `\:N`.

**1.45.0:** 🎞 Nowa szata „ciemnia”. Tło jest teraz w neutralnym grafitowym odcieniu zamiast granatu, więc nie przekłamuje kolorów zdjęć, tak jak w programach do obróbki zdjęć. Kolor zostaje dla zdjęć i tego, co wybrane: zaznaczone zdjęcie dostaje neonową obwódkę, a na wykresie lat szare słupki zmieniają się w neon dopiero na wybranym roku. Program ma własną czcionkę (Instrument Sans, licencja OFL), która działa bez internetu i wygląda tak samo na każdym komputerze. Siatka zdjęć nie ma już ramek kart: zostaje samo zdjęcie i cichy podpis. Przyciski na paskach mają tło dopiero pod kursorem, więc pasek zaznaczenia i nagłówek są spokojniejsze, a nazwa projektu się mieści. Emoji na przyciskach (📅 Data, 📍 Miejsce, 🗑 Usuń, menu Pomocy…) zamieniono na ikony liniowe z jednego zestawu, które zmieniają kolor razem z motywem. Pełny podgląd zdjęcia ma neutralnie czarne tło, a dymki podpowiedzi są w grafitowym kolorze.

**1.44.0:** ✨ Neonowe akcenty z umiarem: jedna para kolorów (turkus → fiolet → róż). Gradient na aktywnym module i przyciskach głównych, cienka świecąca linia pod nagłówkiem, turkusowa obwódka zaznaczonych zdjęć, neonowy słupek wybranego miesiąca na wykresie lat, turkusowy pasek przy wybranym folderze w drzewie, gradient w ścieżce folderu, neonowy pasek w oknach i pasku zaznaczenia, turkusowa obwódka fokusu z klawiatury. Poświata tylko w motywie ciemnym i tylko przy tym, co aktywne; w jasnym — te same akcenty w głębszych odcieniach, bez świecenia. Ostrzeżenia (np. licznik kosza) zostają czerwone.

**1.43.0:** 🌍 **Most do domu** — Przeglądarka z domu na innym komputerze (np. w pracy) bez Tailscale i bez VPN-u na tamtym komputerze. W domu: ⚙ Ustawienia → 🌍 Most do domu → Włącz most — Katalogator sam wystawia przez Tailscale Funnel samą Przeglądarkę pod stałym adresem `https://<komputer>.<tailnet>.ts.net/` (Tailscale tylko na komputerze w domu). Wejście tylko długim kluczem (PIN telefonu przez most nie działa), tylko do oglądania (bez usuwania, pilota i pełnego programu); „Nowy klucz” wylogowuje stare połączenia; po restarcie most włącza się sam. W pracy: ⚙ Ustawienia → 🌍 Zdalna biblioteka → wklej link → przycisk 🌍 Dom u góry (albo od razu po starcie); link działa też w zwykłej przeglądarce. Poprawka: okna programu (Ustawienia, Raport, Kosz, wybór folderu) otwierały się pod otwartą Przeglądarką i nie było ich widać.

**1.42.0:** Przeglądarka → 📁 Foldery wygląda jak w Synology Photos: drzewo folderów po lewej ze strzałkami (bez ikonek, liczba zdjęć po najechaniu, sterowanie klawiaturą), u góry klikalna ścieżka „Uporządkowane › Zdjęcia › Zdjęcia z 2010 › Czerwiec w domu”, nad zdjęciami kafelki podfolderów (liczba zdjęć i podfolderów). Folder z samymi podfolderami pokazuje kafelki i przycisk „Pokaż wszystkie zdjęcia z podfolderów”, pusty folder — czytelny pusty stan. Wejście w folder z kafelka albo ścieżki rozwija i podświetla go w drzewie.

**1.41.3:** Przeglądarka: obraz nie drga już przy przewinięciu do samego dołu. Wykres lat i miesięcy chowa się raz przy przewijaniu w dół i wraca przy przewinięciu w górę — wcześniej przy samym dole przeskok wywołany jego schowaniem był brany za ruch w górę i wykres chował się i pojawiał w kółko.

**1.41.2:** Pytania i komunikaty („Usunąć 3 zdjęcia?”, nazwa albumu, PIN…) we własnym oknie programu w kolorze okien — zamiast białego okienka systemowego z nagłówkiem „Komunikat z witryny 127.0.0.1…”: pytanie na górze, wyjaśnienie pod spodem, Enter = OK, Esc = Anuluj, operacje „NA STAŁE” z czerwonym przyciskiem. Pasek zaznaczenia na dole Przeglądarki w tym samym kolorze (z kolorowym paskiem u góry i obwódką), więc nie ginie na tle zdjęć.

**1.41.1:** Okna otwierane nad programem (Pomoc, Ustawienia, Raport, wybór folderu, miejsce, data, telefon…) są teraz wyraźnie widoczne: mocniej przyciemnione i rozmyte tło, okno w innym kolorze (odcień akcentu) z kolorowym paskiem u góry, obwódką i krótką animacją otwarcia — w motywie jasnym i ciemnym.

**1.41.0:** 📖 **Pomoc** (F1 albo menu ?, w Przeglądarce także menu ⋯): instrukcja każdej zakładki z przykładami dla nowego projektu, istniejącego i takiego, w którym zmieniły się foldery (w tym: jak doskanować jeden folder i porównać go z biblioteką), skróty klawiszy, pytania; wyszukiwarka z podświetleniem; F1 otwiera temat zakładki, na której jesteś. 💬 **Podpowiedzi po najechaniu myszką** — czytelne dymki z wyróżnionym skrótem klawisza zamiast systemowych (wyłączane w Pomocy); opisy dla przycisków, które ich nie miały. Poprawki z raportu: 🛠 naprawa odzyskanych filmów nie czyta już przy każdym pliku nagłówków tysięcy filmów z dysku sieciowego (wcześniej ok. 4 min na plik), a wynik każdej naprawy trafia do dziennika; filmy ze starym, nietypowym nagłówkiem, które ffmpeg czyta poprawnie, nie są już zgłaszane jako „nieczytelne”, a przy zdjęciach raport podaje powód (same zera, ucięty JPEG, HEIC z rozszerzeniem .jpg); raport diagnostyczny pokazuje, czy skan naprawdę trwa; zakładka Raport liczy się raz (wcześniej 18–37 s przy każdym otwarciu dużego projektu).

**1.40.0:** 🕰 „Tego dnia” ma dwa tryby: **📅 Ta sama data** (ten sam dzień w różnych latach) i nowy **📍 To samo miejsce** — zdjęcia zrobione w tym samym miejscu w różnych latach, pogrupowane latami („7 lat temu · 2 zdjęcia”). Miejsce wybierasz z listy znanych miejsc (od tych z największej liczby lat), promień ± 100 m / 300 m / 1 km / 5 km. W podglądzie zdjęcia z lokalizacją — przycisk „🕰 To samo miejsce”. Poprawka: na pasku zaznaczenia dla dokumentów jest teraz „📷 Zmień na zdjęcia” (wcześniej zawsze „Zmień na dokumenty”), a w podglądzie dokumentu podświetla się właściwy typ.

**1.39.0:** Zmiana miejsca zdjęcia: w oknie lokalizacji od razu widać „Znane miejsca” — miejscowości (i kraje za granicą), które już są w bibliotece, od najczęstszych, z liczbą zdjęć. Jedno kliknięcie ustawia pinezkę; wpisywanie w wyszukiwarce zawęża też tę listę. Działa również przy zmianie miejsca wielu zaznaczonych zdjęć.

**1.38.1:** Podgląd zdjęcia: obraz nie nachodzi już na pasek narzędzi — mieści się pod nim (także gdy pasek zawija się w wąskim oknie), strzałki ‹ › wyśrodkowane względem obrazu.

**1.38.0:** Przeglądarka:
- **Typ pliku: 📷 Zdjęcie ⇄ 📄 Dokument** w podglądzie, a hurtem na pasku zaznaczania. W uporządkowanej bibliotece plik od razu trafia do właściwego folderu: Dokumenty/Dokumenty z RRRR albo Zdjęcia/Zdjęcia z RRRR/<miesiąc>, do istniejącego folderu tego miesiąca, np. „Kwiecień w domu”. Jest „Cofnij”, który przywraca też miejsce pliku. Albumy, ulubione i osoby przenoszą się razem z plikiem.
- **Nowy pasek w podglądzie**: przyciski w grupach na ciemnym tle, przez które nie prześwituje pasek Przeglądarki. Aktywny przycisk ma niebieskie podświetlenie, złoty kolor zostaje tylko dla ★ Ulubionych.
- **Komunikaty o wersji widać też nad otwartą Przeglądarką**: zarówno „Masz najnowszą wersję”, jak i pasek nowej wersji.

**1.37.0:** Przeglądarka:
- **🔀 Serie i porównywanie.** Nowy widok „Serie” zbiera ujęcia tej samej sceny zrobione w ciągu paru sekund. Okno porównania pokazuje 2–4 zdjęcia obok siebie i powiększa wszystkie naraz (kółko myszy, przeciąganie). Pasek ostrości podpowiada najlepsze ujęcie, a najostrzejsze jest od razu oznaczone ✓. „Zostaw zaznaczone, resztę do kosza” można cofnąć. Porównać można też zaznaczone zdjęcia i serię otwartą w podglądzie.
- **📦 Eksport kopii** do wybranego folderu: rozmiar, jakość, usunięcie GPS i znak wodny.
- **✎ Zmiana nazw hurtem** według wzoru ({data}, {czas}, {miejsce}, {aparat}, {folder}, {nazwa}, {nr}) z podglądem i „Cofnij”. Albumy, ulubione, osoby i pliki .xmp trafiają za zdjęciem.
- **📷 Dane aparatu i histogram** we ℹ Właściwościach: przysłona, czas, ISO, ogniskowa, obiektyw i lampa oraz ostrzeżenie o prześwietleniu.
- **Filtry** (lejek na pasku): aparat albo telefon i pora dnia (rano, dzień, wieczór, noc).
- **👤 Imię wpisujesz wprost pod twarzą** na liście Osób. To samo imię przy dwóch twarzach łączy je w jedną osobę.

**1.36.0:** Przeglądarka: **☑ Zaznacz** na pasku włącza tryb zaznaczania (klik zaznacza, „☑ Wszystkie” i „☐ Odznacz” zostają pod ręką); **zaznaczanie oknem**: wystarczy przeciągnąć myszą po zdjęciach (z Ctrl albo Shift dochodzi do zaznaczonych); **suwak wielkości miniatur** na pasku (także Ctrl + kółko); nowy widok **📁 Foldery** z drzewem katalogów, w którym widać, ile zdjęć jest w każdym folderze, a po kliknięciu pokazują się jego zdjęcia (opcjonalnie z podfolderami); **🗂 znaczek albumu** na miniaturze i w podglądzie mówi, że zdjęcie jest już w albumie; **✏ tryb Edycji**: narzędzia edycji obrazu (✏ Edytuj, edycja hurtem, szybkie ↺ ↻ ✏ na miniaturach po najechaniu myszą, pole „zastępuj oryginały”) są widoczne tylko w nim. Poza nim Przeglądarka służy do spokojnego oglądania.

**1.35.0:** **🙈 Ukryte albumy**, np. „Praca”. W widoku albumu przycisk „🙈 Ukryj w Przeglądarce” sprawia, że zdjęcia z tego albumu znikają z osi czasu, mapy, wyszukiwania, „Tego dnia” i „Osób”. Na telefonie i w serwerze 24/7 nie widać ani tego albumu, ani jego zdjęć. Sam album zostaje w ⭐ Kolekcjach i w programie na komputerze można go otworzyć, a pliki zostają na dysku. Główny przełącznik w ⭐ Kolekcjach albo w menu ⋯ („🙈 Ukrywaj wybrane albumy”) jednym kliknięciem włącza i wyłącza ukrywanie wszystkich takich albumów. Zmienić to można tylko na komputerze.

**1.34.0:** **✏ Edycja hurtem** zaznaczonych zdjęć. Na pasku zaznaczania jest nowy rząd przycisków: ↺ W lewo, ↻ W prawo, ⟳ 180°, ⇋ Odbij i ✨ Auto (automatyczny balans bieli, jasność i kontrast). Obok jest pole **„zastąp oryginały”**: gdy jest zaznaczone, zmienione zdjęcie zachowuje nazwę i miejsce, a oryginał trafia do kosza programu (Odłożone/Usunięte). Bez zaznaczenia obok powstaje kopia „(edytowane)”. Praca idzie w tle z paskiem postępu, a na końcu jest „Cofnij” dla całej partii. Data, miejsce i EXIF zostają zachowane, filmy są pomijane.

**1.33.1:** OpenCV przypięte do sprawdzonej serii 4.x — wykrywanie twarzy działa tak samo na każdym komputerze.

**1.33.0:** **Przeglądarka jest teraz główną częścią programu.** Po uruchomieniu otwiera się od razu (w ⚙ Ustawieniach można wrócić do ekranu wyboru). Jej zakładka jest pierwsza, a uporządkowana biblioteka sama trafia do Przeglądarki: pusta Przeglądarka dodaje ją automatycznie, w pozostałych przypadkach wystarczy przycisk „📚 Dodaj bibliotekę”. **👤 Osoby — wykrywanie twarzy:** program znajduje twarze na zdjęciach i grupuje je w osoby, w całości na tym komputerze, bez wysyłania do internetu. Używa modeli OpenCV YuNet i SFace; model rozpoznawania (38 MB) pobiera się raz przy pierwszym użyciu. Osobie nadajesz imię, a potem wpisujesz je w wyszukiwarkę (np. „Ania 2019”). Rozpoznane jako kilka osób łączysz przez Ctrl+klik i „🔗 Połącz”, obcych z tła ukrywasz. Nowe zdjęcia są przeglądane same po każdym skanie, a imiona osób widać w podglądzie zdjęcia. **ℹ Właściwości** (przycisk w podglądzie albo klawisz I) pokazują folder i pełną ścieżkę pliku, rozmiar, wymiary albo długość filmu, skąd pochodzi data, aparat, miejsce i osoby. Są też przyciski „📂 Pokaż w folderze”, który otwiera Eksplorator z zaznaczonym plikiem, i „📋 Kopiuj ścieżkę”.

**1.32.1:** Neonowe ikony na pasku Przeglądarki: Oś czasu, Mapa, Kolekcje, Tego dnia, Szukaj, Wszystko, Zdjęcia, Filmy i Dokumenty. Aktywny widok i rodzaj nie jest już pełnym niebieskim prostokątem. Ma szklane podświetlenie z jasną kreską u dołu, więc ikony są dobrze widoczne. Ikony liniowe w ciemnym motywie mają delikatną neonową poświatę i pasują do nowych.

**1.32.0:** Nowy, spójny zestaw ikon. Na paskach programu i Przeglądarki emoji zastąpiły ikony liniowe w kolorach modułów: Porządkowanie, Przeglądarka i Wyślij — cyjan, Sprzątanie — niebieski z bursztynową iskrą, Biblioteka — fiolet, Kosz — szary, Odzyskaj — niebieski, Ustawienia i Dyski — stalowy (Dyski z zieloną diodą), Statystyki — cyjan z fioletem. W jasnym motywie kolory są ciemniejsze, żeby były czytelne. Ikony 3D są na ekranie „Czym się dziś zajmujemy?”, w nagłówkach okien Kosz, Odzyskiwanie i Ustawienia oraz na pustej Przeglądarce i Bibliotece.

**1.31.0:** Czytelniejsza nawigacja w Przeglądarce i Bibliotece. Pasek programu z modułami (🗂 Porządkowanie · 🧹 Sprzątanie · 🔭 Przeglądarka · 📚 Biblioteka, kosz, odzyskiwanie, ustawienia) zostaje teraz widoczny nad zdjęciami w zwartej formie. Podświetlony jest otwarty moduł, a jedno kliknięcie przenosi do innego. Schowany pasek wraca listwą „▾ Menu Katalogatora”, która nie zasłania już wyszukiwarki. Pasek Przeglądarki mieści się w jednej linii i jest podzielony na grupy: widoki, szukanie, rodzaje plików i narzędzia. Na węższym ekranie zostają same ikony z podpowiedziami. „▴ Schowaj ten pasek” jest teraz w menu ⋯. Wszystkie funkcje działają jak wcześniej.

**1.30.2:** Zmiana 📍 miejsca i 📅 daty idzie **w tle**: po „Zapisz” okno znika od razu i można dalej przeglądać, a w prawym górnym rogu widać pasek postępu (np. „📍 Zapisuję lokalizację · 120 / 400”). Kilka zmian ustawia się w kolejkę; na końcu komunikat z „Cofnij”.

**1.30.1:** 🛠 Naprawa filmów **bez pytania o wzorzec**: program sam szuka na dyskach (biblioteka, Przeglądarka,
Wideo, Zoom, Pobrane) działających filmów z tym samym „podpisem” nagrywającego programu (atom ftyp) i po kolei
próbuje ich jako wzorców; ten, który zadziałał, służy następnym plikom. Lista odzyskanych pokazuje stan: dobry /
⚠ bez indeksu / ⚠ uszkodzony / 📄 plik tekstowy (np. „.d.mts” — kod programu, nie film) / ∅ pusty.

**1.30:** 🛟 Odzyskiwanie — **🛠 Napraw filmy**: odzyskane filmy, których nie da się otworzyć (Windows: 0xc00d36e5).
Program sprawdza budowę pliku MP4: gdy indeks jest (plik ucięty / uszkodzone fragmenty) — przepisuje go ffmpeg-iem;
gdy indeksu (`moov`) brak — co zwykle dzieje się przy odzyskiwaniu „po sygnaturze” (pliki `1.mp4`, `2.mp4`…
w folderze `mp4`) — odbudowuje go darmowym programem **untrunc** na podstawie **wzorca**: działającego filmu z tego
samego źródła (inne nagranie Zoom, film z tego samego telefonu). Wynik `<nazwa>_naprawiony.mp4` obok oryginału.

**1.29.9:** 🛟 Odzyskiwanie — każdy odzyskany plik jest sprawdzany: **∅ pusty** (same zera — dysk SSD wyczyścił
zawartość, TRIM; nie do odzyskania), **⚠ uszkodzony** (zły początek pliku) albo dobry; dobre na początku listy,
podsumowanie „działa X z Y”.

**1.29.8:** 🛟 Odzyskiwanie — czytelny postęp (etap 1–3, bez „krzaków” z dziennika Windows File Recovery) i podpowiedź:
dawno usunięte pliki często tracą nazwę i folder, więc gdy szukanie w folderze nic nie da — cały dysk, tylko rodzaj.

**1.29.7:** 🛟 Odzyskiwanie — folder na odzyskane pliki bez spacji: `<dysk>:\Odzyskane_Katalogator` (Windows File
Recovery nie przyjmuje ścieżek ze spacjami i polskimi literami — błąd 0x80070356 także na pendrivie); własny folder
— tylko w rodzaju `D:\Odzysk`; pendrive / dysk USB podpowiadany jako pierwszy, wybór zapamiętany.

**1.29.6:** 🛟 Odzyskiwanie — Windows File Recovery nie zapisuje na dyski sieciowe (błąd 0x80070356): odzyskane
pliki zapisujesz na pendrive / dysk USB (przycisk ⟳ odświeża listę po podłączeniu), potem możesz je przenieść na
NAS · czytelny dziennik (wcześniej pierwsza linia była nieczytelna) i podpowiedzi po polsku przy typowych błędach.
Przywracanie z koszy i kopii zapasowej — nadal do dowolnego folderu, także sieciowego.

**1.29.5:** 🛟 Odzyskiwanie — skrypt i dziennik Windows File Recovery leżą lokalnie (w danych programu, kilka KB),
na dysk docelowy idą tylko odzyskane pliki — start działa także z zapisem na dysk sieciowy; gdy odzyskiwanie nie
ruszy (brak zgody administratora) — komunikat i *↺ Spróbuj ponownie*; błąd dostępu do miejsca zapisu widać
w dzienniku · kosz programu (Odłożone) zwinięty w jedną linię, z datą pliku zamiast „usunięty”.

**1.29.4:** filmy w folderach nazwanych rokiem (`2007`, `2009-07 Mazury`, `2016_08`) to własne nagrania — trafiają do
`Filmy\Filmy z <rok>\<miesiąc>` zamiast do `Filmy\Inne` (gdy data pliku nie pasuje do folderu, liczy się rok
z folderu, z uwagą „data z nazwy folderu — sprawdź”). Filmy, które wcześniej trafiły do `Filmy\Inne`, przy nowej
propozycji drzewa przenoszą się w obrębie biblioteki do drzewa lat. Filmy kinowe („Avatar (2009)”) zostają w Inne.

**1.29.3:** 🛟 Odzyskiwanie — odzyskane pliki można zapisać także na **dysku sieciowym** (np. Z: na NAS-ie) —
przydatne, gdy w komputerze jest tylko dysk C:. Windows File Recovery działa jako administrator i nie widzi
zmapowanych liter, więc program sam podłącza udział (`net use`, zapisane hasło Windows), a w razie potrzeby używa
ścieżki `\\serwer\udział`. Gdy odzyskiwanie skończy się błędem — w oknie widać ostatnie komunikaty.

**1.29.2:** 🛟 Odzyskiwanie — **skąd i dokąd**: *Gdzie był* (Pobrane, Pulpit…, cały dysk albo *📂 Inny folder…*)
oraz *Przywróć do*: z koszy i kopii — **na oryginalne miejsce** albo **do wybranego folderu**; głębokie szukanie —
odzyskane pliki na wybranym dysku („Odzyskane_Katalogator”) albo w **dowolnym folderze na innym dysku**
(w komputerze albo USB — dysków sieciowych Windows File Recovery nie obsługuje).

**1.29.1:** 🛟 Odzyskiwanie — **wybrane formaty**: pod rodzajem lista formatów (np. dla filmów MP4, MOV, AVI, MKV,
MTS…; klik pomija format), pole na własne rozszerzenia (np. `braw, psd`), nowe rodzaje 🎵 Muzyka i 🗜 Archiwa;
filtr działa w koszach, kopii zapasowej, Windows File Recovery i w wynikach.

**1.29:** **🛟 Odzyskiwanie usuniętych plików** (przycisk 🛟 w nagłówku, czwarty kafelek na starcie): wybierasz
rodzaj (zdjęcia / filmy / dokumenty), fragment nazwy, skąd zniknęły (Pobrane, Pulpit, Dokumenty…, cały dysk, karta
pamięci) i jak dawno. Najpierw program przeszukuje **kosze Windows na wszystkich dyskach** (przywraca na oryginalne
miejsce), **kopię zapasową** (pliki, których nie ma już w bibliotece) i kosz programu. Potem **głębokie szukanie**
nakładką na **Windows File Recovery** (darmowy program Microsoftu — instalacja jednym przyciskiem): tryb *dokładny*
sięga daleko w przeszłość, także po opróżnieniu kosza, formatowaniu i na kartach z aparatu. Odzyskane pliki trafiają
na **inny dysk** (pendrive / USB), do folderu „Odzyskane_Katalogator”, z miniaturami i *🔭 Przeglądaj na osi
czasu*. Windows pyta o zgodę administratora; przerwanie — zamknięcie okna „Katalogator - odzyskiwanie”. Na dyskach
SSD szanse spadają z minuty na minutę (TRIM) — program ostrzega.

**1.28.1:** Przeglądarka — **⇅ kolejność**: od najnowszych (domyślnie) albo od najstarszych; dotyczy zdjęć na osi
czasu, lat i miesięcy, wyników szukania, albumów i „Tego dnia” (zapamiętana; na telefonie w menu ⋯, tam też 📤 Wyślij).

**1.28:** **✏ Edycja zdjęć** w podglądzie (przycisk ✏ Edytuj albo klawisz **E**): obrót ⟲ ⟳, odbicie ⇋, ✂ przycięcie
(dowolnie, 1:1, 4:3, 3:2, 16:9, pion 4:5 / 9:16; klawisz C), jasność, kontrast, nasycenie, balans bieli (temperatura
i odcień), *✨ Auto*, *◐ przytrzymaj: przed* (też spacja). Zapis w pełnej rozdzielczości z datą, aparatem i GPS
oryginału — jako kopia „<nazwa> (edytowane).jpg” obok albo *Zastąp oryginał* (oryginał do Odłożone/Usunięte);
*Cofnij* w komunikacie · **☑ Zaznaczanie wielu** w siatce: kółko na miniaturze, Ctrl+klik, Shift+klik (zakres),
Ctrl+A, na telefonie przytrzymanie palcem → pasek: 📅 Data (z zachowaniem odstępów albo ta sama dla wszystkich),
📍 Miejsce, 📄 Dokument, ＋ Album, ⬇ ZIP, 🗑 Usuń · **⬇ ZIP** zaznaczonych i całego albumu (oryginały, pakowane w locie)
· **🔗 Udostępnij album** — link bez PIN-u do jednego albumu (oglądanie, pobieranie, ZIP; *Wyłącz link* w każdej
chwili); działa przez serwer telefonu: sieć domowa i Tailscale · **📤 Wyślij** — zdjęcia i filmy z telefonu
(albo z innego komputera) prosto do biblioteki: `Z telefonu\<RRRR-MM>` (miesiąc z EXIF-u), ten sam plik drugi
raz nie tworzy kopii; wymaga *Pozwól sterować z telefonu* · **⚙ Ustawienia** (nagłówek) — w jednym oknie: motyw,
start z Windows, telefon (włącz / wyłącz, sterowanie, PIN), odświeżanie Przeglądarki, aktualizacje, kopia zapasowa ·
**💾 Kopia zapasowa** biblioteki na drugi dysk / NAS: tylko nowe i zmienione pliki, z kopii nic nie znika, bez
folderu Odłożone; automatycznie po porządkowaniu i raz na dobę · **🔍 Sprawdź pliki** — suma SHA-1 każdego pliku:
wykrywa uszkodzenia dysku (zawartość inna przy tej samej dacie i rozmiarze), zdjęcia, które się nie otwierają,
i uszkodzone pliki w kopii; *↺ Przywróć z kopii* / *💾 Napraw kopię*; przerwane sprawdzanie rusza od niesprawdzonych.

**1.27:** w podglądzie zdjęcia: *📄 To dokument* (klawisz D) — przełącza zdjęcie ↔ dokument (filtr 📄 Dokumenty,
decyzja widoczna w projekcie) · *📅 Data* — zmiana daty zrobienia, zapis w pliku (JPEG: EXIF bez zmiany obrazu;
inne formaty i filmy: .xmp obok, ręczna data wygrywa przy skanie), opcjonalnie przesunięcie wszystkich zdjęć z tego
dnia o tyle samo (zły zegar aparatu); zmiana widoczna od razu w innych projektach i w Przeglądarce.

**1.26:** ekran startowy — trzy kafelki: 🗂 Porządkowanie, 🧹 Sprzątanie, 🔭 Przeglądarka (klawisze 1/2/3, Esc —
zostań przy ostatnim) · Przeglądarka: pasek programu i pasek Przeglądarki chowane strzałką (▴ / ▾, zapamiętane;
pasek programu domyślnie schowany) · filtr: Wszystko / 📷 Zdjęcia / 🎬 Filmy / 📄 Dokumenty (foldery „Dokumenty…”
i Twoje decyzje) · lokalizacja dla wielu zdjęć: miniatury pozostałych zdjęć z tego dnia, klik — pomiń / dołącz.

**1.25:** decyzje (dokument / zdjęcie / śmieci) i wyniki analizy idą za plikiem do biblioteki — po porządkowaniu
te same zdjęcia nie wracają do przejrzenia (dla już uporządkowanych odtwarzane przy otwarciu projektu) · Dokumenty:
*Ta strona → 📷 zdjęcia / 📄 dokumenty* i *Wszystkie pozostałe → 📷 zdjęcia* · wykrywacz dokumentów nie myli
faktur z długimi pasami (blacha, żaluzje) z tekstem — przy „Analizuj ponownie” oceniani są od nowa tylko kandydaci.

**1.24.2:** wspólny kosz w miejscu docelowym tylko dla źródeł z tego samego dysku (np. Z:\mbarczykmb → Z:\Uporządkowane)
— z innych dysków (Y:, C:) odłożenie zostaje w ich „Odłożone”, bo przeniesienie między dyskami to kopiowanie przez
sieć · licznik kosza z bazy (natychmiast), pełne liczenie po otwarciu okna · Podobne po odłożeniu bez liczenia od nowa
· zapis decyzji czeka na swoją kolej zamiast „database is locked”.

**1.24:** filmy z nieczytelnym nagłówkiem („Invalid argument”, stare 3GP/MP4) — data i GPS z ffmpeg (przy
następnym skanie; filmy z datą „z pliku” czytane jednorazowo jeszcze raz) · Podobne: *▣ Jedna grupa na ekran*
(←/→, Z, **Enter** — odłóż i następna, **S** — zostaw wszystkie; zapis w tle) · Przeglądarka doczytuje zdjęcia
przy przewijaniu · Drzewo: *🔵 Uwagi hurtem* — każdy rodzaj uwag („data z pliku”, „bez GPS”…) przyjmowany jednym
kliknięciem, nie wraca po nowym drzewie, z cofaniem · Drzewo: *▶ Próba: tylko ten folder* — porządkowanie
jednego folderu (z podfolderami), żeby sprawdzić wynik przed całością.

**Jeden kosz w miejscu docelowym** (od 1.23): przy porządkowaniu wszystko, co odkładasz (duplikaty, podobne,
nieostre, śmieci, 🗑 usunięte), trafia do `<miejsce docelowe>\Odłożone\<kategoria>\<źródło>\…` (np.
`Z:\Uporządkowane\Odłożone\Duplikaty\Y\…`). Między dyskami: kopia + sprawdzenie rozmiaru + usunięcie oryginału.
🗑 Kosz → *📦 Przenieś je tam* — jednorazowo przenosi stare „Odłożone” ze źródeł (↶ Cofnij dalej działa).
Gdy miejsce docelowe jest niedostępne, kosz jest jak dawniej w folderze źródłowym. Sprzątanie — bez zmian.

**1.22.1 — audyt:** odkładanie / cofanie / usuwanie zapisuje bazę po każdym pliku (wcześniej przenoszenie setek
plików po sieci blokowało bazę na minuty i decyzje 📷/📄/🗑 kończyły się „database is locked”); grupy podobnych
liczone raz naraz i zapamiętane w bazie projektu (po ponownym uruchomieniu od razu); szybsza lista śmieci.
Przeglądarka: ⋯ → rozmiar miniatur (też Ctrl + kółko), nazwy pod miniaturami, chowanie pasków przy przewijaniu,
⛶ pełny ekran.

**Po restarcie komputera** (od 1.21): włączony telefon jest zapamiętany — po starcie programu włącza się sam, z tym
samym PIN-em i adresem; zamknięcie okna go nie wyłącza (program pracuje w tle, okno otwiera zwykły skrót).
W oknie 📱 opcja *Uruchamiaj Katalogator razem z Windows* (wpis w HKCU\…\Run, `Katalogator.exe --w-tle`,
usuwany przy odinstalowaniu) — telefon działa od razu po włączeniu komputera.

**🎬 Filmy w każdym formacie — także bardzo stare** (2000–2012): AVI (DivX, Xvid, MS-MPEG4, MJPEG z aparatów),
MPG/VOB, MOD/TOD/MTS z kamer (przeplot usuwany), 3GP z telefonów, WMV, FLV, DV… Miniatura = klatka z filmu;
odtwarzanie w oknie (Drzewo, Duplikaty: ▶, Biblioteka, Przeglądarka, telefon): MP4/MOV/WebM — oryginał, inne —
przerabiane w locie na MP4 (zapasowo WebM), bez przewijania. Oryginalny plik się nie zmienia. Wymaga ffmpeg —
jest w instalatorze (wersja przenośna bez ffmpeg odtwarza tylko MP4/WebM).

**⏳ Praca w tle** — w lewym dolnym rogu okna (także w Bibliotece i Przeglądarce): wczytywanie miniatur z paskiem
(np. 12 / 40), dłuższe wczytywanie danych, wyniki dużego projektu po starcie i skan Przeglądarki (także samoczynny).
**🔍 Duplikaty**: kliknij miniaturę grupy albo 🔍 przy pliku — duże zdjęcie, kółko myszy = powiększenie,
**← →** między kopiami z grupy, *Delete* = do kosza, *Esc* zamyka.

**🗑 Kosz i szybkie przeglądanie**: w Duplikatach (200 grup na stronę) i Podobnych *Odłóż zaznaczone kopie i pokaż
kolejne* — kopie od razu trafiają do kosza (folder `Odłożone`), przejrzane grupy znikają, a grupy *zostaw wszystkie*
są zapamiętane jako przejrzane (*↺ pokaż przejrzane* przywraca je). Opcja *od razu usuń na stałe* (identyczne kopie,
oryginał zostaje) kasuje tylko tę partię. Przycisk **🗑** w nagłówku (w obu trybach) pokazuje, ile leży w koszu,
i opróżnia wybrane kategorie.

**📍 Lokalizacja — dodaj, zmień, usuń**: na mapie **przeciągnij pinezkę** w nowe miejsce (dymek pinezki:
*✖ Usuń lokalizację*); w podglądzie zdjęcia **📍 Dodaj / Zmień miejsce** (klawisz *L*) — kliknij na mapie albo wyszukaj
miejscowość, opcjonalnie *także pozostałe zdjęcia z tego dnia bez lokalizacji* (aparat bez GPS na wycieczce).
Zapis w samym pliku: **JPEG** — GPS w EXIF (obraz bajt w bajt bez zmian, data modyfikacji zachowana; widzą to
Windows, Google Zdjęcia, telefony), **HEIC/PNG/RAW/filmy** — plik `.xmp` obok (Lightroom, darktable, digiKam).
Zawsze z **↶ Cofnij**; zmiana od razu widoczna w innych projektach i w Przeglądarce.

**🗑 Usuń — wszędzie, gdzie widać plik**: kafelki i podgląd w Bibliotece i Przeglądarce (także klawisz *Delete*),
zakładki Duplikaty, Dokumenty, Podobne, Nie z aparatu, Śmieci, 🌳 Drzewo, duży podgląd oraz telefon (pilot, gdy
pozwolono sterować). Plik trafia do kosza programu `<folder>/Odłożone/Usunięte/…` — działa też na dyskach sieciowych,
gdzie nie ma Kosza Windows — i od razu można go **↶ Cofnąć**. Na stałe: tryb 🧹 Sprzątanie → *Usuwanie*.

11. **🧹 Sprzątanie** (przełącznik trybów u góry: 🗂 Porządkowanie | 🧹 Sprzątanie | 🔭 Przeglądarka) — porządki
    **na miejscu**, bez kopiowania i bez nowego drzewa: zaznacz foldery → *Skanuj* → *Szukaj duplikatów* →
    zakładki **Duplikaty** i **🗑 Śmieci** (puste, tymczasowe, skróty, ikony, miniatury) → *Odłóż* (do `Odłożone`,
    można cofnąć) → sekcja **Usuwanie** → *Usuń na stałe…* (tylko to, co odłożone; na My Cloud nie ma Kosza).

10. **🔭 Przeglądarka** (przycisk u góry) — zwykła przeglądarka zdjęć, niezależna od porządkowania: *＋ Dysk lub
    folder* → wybierz dyski/foldery → *Skanuj* (tylko odczyt, nic nie jest zmieniane). Zdjęcia z nich zobaczysz na
    osi czasu z wykresem (słupek = miesiąc, kliknij, żeby go otworzyć) i na mapie; działa też *Na telefon*.
    **🔍 Szukaj**: „Hel”, „Włochy 2022”, „lipiec 2019”, fragment nazwy. **⭐ Kolekcje**: ulubione (☆ albo F w podglądzie)
    i albumy; **▶ Pokaz** slajdów; **📅 Oś czasu tego obszaru** na mapie; **🕰 Tego dnia** — zdjęcia z tego samego dnia
    w poprzednich latach, pogrupowane latami („5 lat temu”), ‹ › poprzedni/następny dzień, ± 3 dni / ± tydzień,
    podpowiedź najbliższego dnia ze zdjęciami; na pilocie w telefonie — karta z miniaturami. W podglądzie kółko
    myszy powiększa. Nowe zdjęcia z dysków dopisują się same (przy starcie i co 6 h).
    **Zestawy dysków** (lista 📂 na pasku, ＋ nowy): np. „Rodzina” i „Praca” — każdy z własnymi dyskami.

Projekty (ustawienia, bazy, dziennik): `%LOCALAPPDATA%\Katalogator\projekty\`. Program działa lokalnie
(127.0.0.1); do internetu łączy się tylko mapa (kafelki map OpenStreetMap — bez żadnych danych o zdjęciach)
i sprawdzanie aktualizacji. Udostępnianie na telefon włączasz sam i wyłączasz jednym przyciskiem. Zamknięcie okna w trakcie zadania nie przerywa pracy —
ponowne uruchomienie otwiera okno działającego programu; przerwane zadania wznawiają się od miejsca przerwania.

### Biblioteka na telefonie 24/7 (Raspberry Pi)

Komputer nie musi być włączony: galerię (oś czasu + mapa, tylko oglądanie, PIN) udostępnia Raspberry Pi,
czytając bibliotekę prosto z dysku My Cloud. Z Tailscale działa także poza domem, bez otwierania portów.

**Potrzebne:** Raspberry Pi 4 (2 GB) albo 5, zasilacz, karta microSD 16 GB+ (razem ok. 250–350 zł;
wystarczy też Pi 3B+), kabel sieciowy do routera. Pobór prądu ok. 3–5 W.

1. **Raspberry Pi Imager** (na komputerze) → *Raspberry Pi OS Lite (64-bit)* → w ustawieniach (⚙) włącz **SSH**,
   ustaw użytkownika i hasło → zapisz na kartę → włóż kartę do Pi, podłącz kabel sieciowy i zasilanie.
2. Na komputerze: `ssh uzytkownik@raspberrypi.local` (PowerShell), potem:
   ```
   curl -fsSL https://raw.githubusercontent.com/mbarczykmb-afk/chmura/HEAD/serwer/instaluj-rpi.sh -o instaluj-rpi.sh
   bash instaluj-rpi.sh
   ```
   Skrypt zapyta o adres dysku (np. `\\192.168.100.28\Public`), folder biblioteki i PIN, podłączy dysk
   **tylko do odczytu**, zainstaluje galerię jako usługę (startuje sama po włączeniu prądu) i Tailscale
   (otwórz link, który wyświetli, i zaloguj się tym samym kontem co w telefonie).
3. W telefonie: aplikacja **Tailscale** (to samo konto) → w przeglądarce adres podany na końcu instalacji
   (`http://100.x.x.x:8080/`) → PIN. Dodaj stronę do ekranu głównego — działa jak aplikacja.
4. Nowe zdjęcia w bibliotece pojawiają się w galerii same (skan co 6 godzin; pierwszy — kilkanaście minut
   przy 50 tys. zdjęć). Aktualizacja: uruchom `bash instaluj-rpi.sh` jeszcze raz.

W panelu Tailscale (*Machines → Raspberry Pi → Edit route settings*) zatwierdź podsieć — wtedy telefon
poza domem widzi też sam dysk (SMB, np. w menedżerze plików), jak w wariancie z komputerem.

<details><summary>Dla zaawansowanych: uruchomienie z Pythona / linia poleceń</summary>

```
py -m pip install -r requirements.txt
py -m katalogator                 # okno aplikacji
py -m katalogator skanuj Z:\      # skan w konsoli + raport HTML
py -m katalogator raport
py -m katalogator galeria --folder Z:\Biblioteka --pin 1234   # galeria dla telefonu (serwer)
```
</details>

ffmpeg (https://ffmpeg.org, licencja GPL) — kompilacja z pakietu imageio-ffmpeg, dołączana do instalatora jako
osobny program `ffmpeg\ffmpeg.exe` (podgląd i miniatury filmów).
