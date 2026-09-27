# Mapowanie udzialu WD My Cloud jako dysku sieciowego w Windows.
# Uruchomienie (PowerShell):
#   powershell -ExecutionPolicy Bypass -File .\mapuj-dysk.ps1
param(
    [string]$Adres  = "",
    [string]$Litera = "Z"
)

function Info($t) { Write-Host "[..] $t" -ForegroundColor Cyan }
function Ok($t)   { Write-Host "[OK] $t" -ForegroundColor Green }
function Blad($t) { Write-Host "[!!] $t" -ForegroundColor Red }

# 1. Adres dysku
if (-not $Adres) {
    Info "Szukam dysku pod nazwa WDMYCLOUD..."
    try {
        $Adres = (Resolve-DnsName WDMYCLOUD -ErrorAction Stop |
                  Where-Object { $_.IPAddress -match '^\d+\.\d+\.\d+\.\d+$' } |
                  Select-Object -First 1).IPAddress
    } catch { }
    if ($Adres) { Ok "Znaleziono: $Adres" }
    else {
        Blad "Nie znaleziono po nazwie."
        Write-Host "Adres IP sprawdzisz w panelu dysku (Ustawienia > Siec) lub w routerze."
        $Adres = Read-Host "Podaj adres IP dysku (np. 192.168.1.50)"
    }
}

# 2. Czy dysk odpowiada i czy port SMB (445) jest otwarty
Info "Sprawdzam polaczenie z $Adres (port 445)..."
$t = Test-NetConnection -ComputerName $Adres -Port 445 -WarningAction SilentlyContinue
if (-not $t.PingSucceeded -and -not $t.TcpTestSucceeded) {
    Blad "Dysk nie odpowiada. Sprawdz kabel, zasilanie, adres IP i czy PC jest w tej samej sieci."
    exit 1
}
if (-not $t.TcpTestSucceeded) {
    Blad "Dysk odpowiada, ale port 445 (SMB) jest zamkniety."
    Write-Host "Panel dysku > Ustawienia > Siec > Uslugi systemu Windows: WL."
    exit 1
}
Ok "Dysk osiagalny, SMB dziala."

# 3. Dane logowania (uzytkownik z panelu dysku, zakladka Uzytkownicy)
$uzytk = Read-Host "Nazwa uzytkownika na dysku"
$haslo = Read-Host "Haslo (jesli uzytkownik nie ma hasla - Enter)" -AsSecureString
$hasloTxt = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($haslo))
if (-not $hasloTxt) {
    Blad "Windows 10/11 czesto blokuje konta bez hasla. Ustaw haslo w panelu dysku (Uzytkownicy) i uruchom skrypt ponownie."
    exit 1
}

# Usun stare polaczenia z tym serwerem (blad 1219 - "wiele polaczen")
net use "\\$Adres" /delete /y 2>$null | Out-Null
net use "\\$Adres\IPC`$" /delete /y 2>$null | Out-Null
cmdkey /delete:$Adres 2>$null | Out-Null

# 4. Logowanie i lista udzialow
Info "Loguje sie..."
$wynik = net use "\\$Adres\IPC`$" $hasloTxt /user:"$Adres\$uzytk" 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    Blad "Logowanie nieudane:"
    Write-Host $wynik
    if ($wynik -match '86|1326|5\b') { Write-Host "=> Zla nazwa uzytkownika lub haslo." }
    if ($wynik -match '1272|3227320323') { Write-Host "=> Windows blokuje dostep goscia. Uzyj konta z haslem." }
    if ($wynik -match '53|67') { Write-Host "=> Nie znaleziono sciezki sieciowej - sprawdz adres." }
    exit 1
}
Ok "Zalogowano."

$udzialy = net view "\\$Adres" 2>&1 | Select-String '^\S.*\s+Dysk|^\S.*\s+Disk' |
           ForEach-Object { ($_ -split '\s{2,}')[0].Trim() }
if (-not $udzialy) {
    Blad "Nie udalo sie pobrac listy udzialow. Wynik:"
    net view "\\$Adres"
    $udzial = Read-Host "Wpisz nazwe udzialu recznie (np. Public)"
} else {
    Write-Host "`nDostepne udzialy:"
    for ($i = 0; $i -lt $udzialy.Count; $i++) { Write-Host "  $($i+1). $($udzialy[$i])" }
    $nr = Read-Host "Numer udzialu do zmapowania"
    $udzial = $udzialy[[int]$nr - 1]
}
net use "\\$Adres\IPC`$" /delete /y 2>$null | Out-Null

# 5. Mapowanie (trwale, z zapamietaniem hasla)
$Litera = $Litera.TrimEnd(':')
net use "${Litera}:" /delete /y 2>$null | Out-Null
cmdkey /add:$Adres /user:"$Adres\$uzytk" /pass:$hasloTxt | Out-Null
$wynik = net use "${Litera}:" "\\$Adres\$udzial" /persistent:yes 2>&1 | Out-String
if ($LASTEXITCODE -eq 0) {
    Ok "Zmapowano \\$Adres\$udzial jako dysk ${Litera}:"
    Start-Process explorer.exe "${Litera}:\"
} else {
    Blad "Mapowanie nieudane:"
    Write-Host $wynik
    exit 1
}
