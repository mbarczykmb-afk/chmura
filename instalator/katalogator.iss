; Instalator Katalogatora (Inno Setup 6). Budowany automatycznie na GitHubie:
;   iscc /DWersja=1.2.0 instalator\katalogator.iss
; Instalacja bez uprawnień administratora, do %LOCALAPPDATA%\Programs\Katalogator.
; Dane użytkownika (projekty, dzienniki) w %LOCALAPPDATA%\Katalogator NIE są usuwane przy odinstalowaniu.

#ifndef Wersja
  #define Wersja "0.0.0"
#endif

[Setup]
AppId={{6B7E3C51-2A5D-4E7B-9C8A-1F4D2E6A9B30}
AppName=Katalogator
AppVersion={#Wersja}
AppVerName=Katalogator {#Wersja}
AppPublisher=Katalogator
AppPublisherURL=https://github.com/mbarczykmb-afk/chmura
AppSupportURL=https://github.com/mbarczykmb-afk/chmura/issues
AppUpdatesURL=https://github.com/mbarczykmb-afk/chmura/releases
DefaultDirName={localappdata}\Programs\Katalogator
DefaultGroupName=Katalogator
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Katalogator-Setup-{#Wersja}
SetupIconFile=..\katalogator\dane\ikona.ico
UninstallDisplayIcon={app}\Katalogator.exe
UninstallDisplayName=Katalogator
VersionInfoVersion={#Wersja}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"

[Tasks]
Name: "pulpit"; Description: "Utwórz skrót na pulpicie"; GroupDescription: "Skróty:"

[InstallDelete]
; aktualizacja: stare biblioteki poprzedniej wersji znikają, zanim wgramy nowe (bez mieszania wersji)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
; wersja „folder”: Katalogator.exe + _internal (Python i biblioteki) — nic nie jest rozpakowywane do %TEMP%
Source: "..\dist\instalacja\Katalogator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Katalogator"; Filename: "{app}\Katalogator.exe"; Comment: "Porządkowanie zdjęć, filmów i plików"
Name: "{autodesktop}\Katalogator"; Filename: "{app}\Katalogator.exe"; Tasks: pulpit

[Run]
Filename: "{app}\Katalogator.exe"; Description: "Uruchom Katalogator"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[UninstallRun]
Filename: "{app}\Katalogator.exe"; Parameters: "--usun-harmonogramy"; Flags: runhidden waituntilterminated; RunOnceId: "UsunHarmonogramy"
