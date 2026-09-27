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

Konfiguracje i skrypty dla wybranej opcji trafią do tego repozytorium.
