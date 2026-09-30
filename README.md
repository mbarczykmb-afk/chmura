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
   - *📱 Na telefon*: kod QR + PIN — telefon w tej samej sieci Wi-Fi (albo z Tailscale — z każdego miejsca)
     ogląda bibliotekę w przeglądarce, tylko do odczytu; działa, dopóki Katalogator jest otwarty.

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
