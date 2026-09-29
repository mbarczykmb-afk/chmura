#!/usr/bin/env bash
# Galeria biblioteki 24/7 na Raspberry Pi (Raspberry Pi OS Lite 64-bit, Bookworm lub nowszy).
#
#   curl -fsSL https://raw.githubusercontent.com/mbarczykmb-afk/chmura/HEAD/serwer/instaluj-rpi.sh -o instaluj-rpi.sh
#   bash instaluj-rpi.sh
#
# Co robi:
#   1. podłącza udział dysku sieciowego (WD My Cloud / NAS) tylko do odczytu w /mnt/mycloud,
#   2. instaluje Katalogatora i uruchamia galerię (oś czasu + mapa) jako usługę — startuje sama po włączeniu Pi,
#   3. instaluje Tailscale — telefon widzi galerię (i dysk) z każdego miejsca, bez otwierania portów w routerze.
# Galeria jest tylko do oglądania (PIN); nic na dysku nie jest zmieniane.
#
# Bez pytań (np. ponowna instalacja): SMB=//192.168.100.28/Public BIBLIOTEKA=Biblioteka PIN=123456 bash instaluj-rpi.sh
set -euo pipefail

REPO="${REPO:-https://github.com/mbarczykmb-afk/chmura.git}"
# najnowsze wydanie (np. v1.5.0) — to samo, co instalator na Windows; ponowne uruchomienie skryptu = aktualizacja
WERSJA_KAT="${WERSJA_KAT:-$(curl -fsSL https://api.github.com/repos/mbarczykmb-afk/chmura/releases/latest \
  | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -1)}"
KATALOG=/opt/katalogator
PUNKT=/mnt/mycloud
UZYTKOWNIK="${SUDO_USER:-$USER}"

pytaj() {  # pytaj ZMIENNA "pytanie" "domyślna"
  local nazwa="$1" pytanie="$2" domyslna="$3" odp
  if [ -n "${!nazwa:-}" ]; then return; fi
  read -r -p "$pytanie [$domyslna]: " odp </dev/tty || true
  printf -v "$nazwa" '%s' "${odp:-$domyslna}"
}

echo "== Galeria biblioteki 24/7 — instalacja =="
pytaj SMB "Adres udziału dysku (z komputera: \\\\192.168.100.28\\Public)" "//192.168.100.28/Public"
SMB="${SMB//\\//}"                       # \\192.168.100.28\Public -> //192.168.100.28/Public
pytaj SMB_UZYTKOWNIK "Użytkownik dysku (puste = gość)" ""
if [ -n "$SMB_UZYTKOWNIK" ]; then
  read -r -s -p "Hasło dysku: " SMB_HASLO </dev/tty || true; echo
fi
pytaj BIBLIOTEKA "Folder biblioteki na dysku (względem udziału)" "Biblioteka"
pytaj PIN "PIN do galerii (cyfry, min. 4)" "$(shuf -i 100000-999999 -n 1)"
pytaj PORT "Port galerii" "8080"

echo "== 1/4 Pakiety =="
sudo apt-get update -qq
sudo apt-get install -y -qq git python3-venv python3-dev cifs-utils libjpeg-dev zlib1g-dev >/dev/null

echo "== 2/4 Dysk sieciowy (tylko odczyt) =="
sudo mkdir -p "$PUNKT"
sudo tee /etc/katalogator-smb >/dev/null <<EOF
username=${SMB_UZYTKOWNIK:-guest}
password=${SMB_HASLO:-}
EOF
sudo chmod 600 /etc/katalogator-smb
OPCJE="ro,credentials=/etc/katalogator-smb,iocharset=utf8,uid=$(id -u "$UZYTKOWNIK"),gid=$(id -g "$UZYTKOWNIK"),_netdev,nofail,x-systemd.automount"
sudo sed -i "\# $PUNKT cifs #d" /etc/fstab
PODLACZONY=""
for WERSJA in 3.0 2.1 2.0 1.0; do  # starsze My Cloud mówią tylko SMB2 albo SMB1
  if sudo mount -t cifs "$SMB" "$PUNKT" -o "ro,credentials=/etc/katalogator-smb,iocharset=utf8,vers=$WERSJA" 2>/dev/null; then
    sudo umount "$PUNKT"; PODLACZONY="$WERSJA"; break
  fi
done
if [ -z "$PODLACZONY" ]; then
  echo "!! Nie udało się podłączyć $SMB — sprawdź adres, użytkownika i hasło, potem uruchom skrypt ponownie."; exit 1
fi
echo "$SMB $PUNKT cifs $OPCJE,vers=$PODLACZONY 0 0" | sudo tee -a /etc/fstab >/dev/null
sudo systemctl daemon-reload
sudo mount "$PUNKT" 2>/dev/null || true
ls "$PUNKT/$BIBLIOTEKA" >/dev/null 2>&1 || echo "Uwaga: nie widzę folderu $PUNKT/$BIBLIOTEKA — galeria pokaże go, gdy się pojawi."

echo "== 3/4 Katalogator i usługa galerii =="
[ -n "$WERSJA_KAT" ] || { echo "!! Nie mogę sprawdzić najnowszej wersji (brak internetu?)"; exit 1; }
echo "Wersja: $WERSJA_KAT"
if [ -d "$KATALOG/.git" ]; then
  sudo git -C "$KATALOG" fetch -q --depth 1 origin "refs/tags/$WERSJA_KAT:refs/tags/$WERSJA_KAT"
  sudo git -C "$KATALOG" checkout -q "$WERSJA_KAT"
else
  sudo git clone -q --depth 1 -b "$WERSJA_KAT" "$REPO" "$KATALOG"
fi
sudo chown -R "$UZYTKOWNIK" "$KATALOG"
python3 -m venv "$KATALOG/venv"
"$KATALOG/venv/bin/pip" install -q --upgrade pip
"$KATALOG/venv/bin/pip" install -q -r "$KATALOG/requirements.txt"
sudo tee /etc/katalogator-galeria.env >/dev/null <<EOF
KATALOGATOR_PIN=$PIN
EOF
sudo chmod 600 /etc/katalogator-galeria.env
sudo tee /etc/systemd/system/katalogator-galeria.service >/dev/null <<EOF
[Unit]
Description=Galeria biblioteki (Katalogator)
After=network-online.target remote-fs.target
Wants=network-online.target

[Service]
User=$UZYTKOWNIK
EnvironmentFile=/etc/katalogator-galeria.env
WorkingDirectory=$KATALOG
ExecStart=$KATALOG/venv/bin/python -m katalogator galeria --folder "$PUNKT/$BIBLIOTEKA" --port $PORT
Restart=always
RestartSec=20
Nice=10

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable katalogator-galeria >/dev/null
sudo systemctl restart katalogator-galeria

echo "== 4/4 Tailscale (dostęp spoza domu) =="
if ! command -v tailscale >/dev/null; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
SIEC="$(ip -4 route | awk '/proto kernel/ && /src/ {print $1; exit}')"
echo "Zaloguj Raspberry Pi do Tailscale (to samo konto co w telefonie) — otwórz link, który się pojawi:"
sudo tailscale up --advertise-routes="$SIEC" --accept-dns=false || true

IP_LAN="$(hostname -I | awk '{print $1}')"
IP_TS="$(tailscale ip -4 2>/dev/null | head -1 || true)"
echo
echo "== Gotowe =="
echo "Galeria w domu:      http://$IP_LAN:$PORT/"
[ -n "$IP_TS" ] && echo "Galeria z Tailscale: http://$IP_TS:$PORT/   (telefon z włączonym Tailscale — działa wszędzie)"
echo "PIN: $PIN"
echo "Pierwsze uruchomienie skanuje bibliotekę (dla 50 tys. zdjęć może to potrwać kilkanaście minut),"
echo "potem nowe zdjęcia dochodzą co 6 godzin. Stan: sudo systemctl status katalogator-galeria"
echo "W panelu Tailscale zatwierdź podsieć $SIEC (Edit route settings) — wtedy z telefonu widać też sam dysk (SMB)."
