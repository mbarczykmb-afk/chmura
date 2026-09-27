# Ustawia ten PC jako "bramke" Tailscale do sieci domowej (subnet router),
# zeby telefon poza domem widzial dysk My Cloud pod jego lokalnym adresem IP.
# Wymaga: zainstalowany i zalogowany Tailscale (https://tailscale.com/download/windows).
# Uruchomienie (PowerShell JAKO ADMINISTRATOR):
#   powershell -ExecutionPolicy Bypass -File .\tailscale-podsiec.ps1
param([string]$AdresDysku = "")

function Info($t) { Write-Host "[..] $t" -ForegroundColor Cyan }
function Ok($t)   { Write-Host "[OK] $t" -ForegroundColor Green }
function Blad($t) { Write-Host "[!!] $t" -ForegroundColor Red }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Blad "Uruchom PowerShell jako Administrator."; exit 1 }

$ts = (Get-Command tailscale -ErrorAction SilentlyContinue).Source
if (-not $ts) { $ts = "$env:ProgramFiles\Tailscale\tailscale.exe" }
if (-not (Test-Path $ts)) {
    Blad "Nie znaleziono Tailscale. Zainstaluj: https://tailscale.com/download/windows i zaloguj sie."
    exit 1
}
& $ts status *> $null
if ($LASTEXITCODE -ne 0) { Blad "Tailscale nie jest zalogowany. Kliknij ikone Tailscale w zasobniku i zaloguj sie."; exit 1 }
Ok "Tailscale dziala."

# Adres dysku: z mapowanego dysku sieciowego albo recznie
if (-not $AdresDysku) {
    $m = Get-SmbMapping -ErrorAction SilentlyContinue |
         Where-Object { $_.RemotePath -match '^\\\\(\d+\.\d+\.\d+\.\d+)\\' } | Select-Object -First 1
    if ($m) { $AdresDysku = $Matches[1]; Ok "Adres dysku z mapowania: $AdresDysku" }
    else    { $AdresDysku = Read-Host "Podaj adres IP dysku My Cloud (np. 192.168.1.50)" }
}
if ($AdresDysku -notmatch '^(\d+\.\d+\.\d+)\.\d+$') { Blad "Niepoprawny adres: $AdresDysku"; exit 1 }
$podsiec = "$($Matches[1]).0/24"
Info "Udostepniam siec domowa $podsiec przez Tailscale..."

& $ts set --advertise-routes=$podsiec
if ($LASTEXITCODE -ne 0) { Blad "Nie udalo sie ustawic trasy."; exit 1 }
Ok "Trasa $podsiec zgloszona."

# PC nie moze zasypiac, gdy jest podlaczony do pradu
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
Ok "Usypianie przy zasilaniu sieciowym wylaczone (ekran moze sie wylaczac)."

Write-Host ""
Write-Host "DOKONCZ W PRZEGLADARCE:" -ForegroundColor Yellow
Write-Host "  1. https://login.tailscale.com/admin/machines"
Write-Host "  2. Przy tym komputerze: ... > Edit route settings > zaznacz $podsiec > Save"
Write-Host "  3. ... > Disable key expiry (zeby nie wylogowal sie po 180 dniach)"
Write-Host ""
Write-Host "TELEFON: aplikacja Tailscale (to samo konto) > wlacz."
Write-Host "  Menedzer plikow (CX File Explorer / Material Files) > SMB > host $AdresDysku"
