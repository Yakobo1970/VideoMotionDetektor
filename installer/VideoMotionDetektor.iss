; Video Motion Detektor Setup - Inno Setup Skript
;
; Packt das mit PyInstaller gebaute, eigenstaendige dist\VideoMotionDetektor\-
; Verzeichnis (fertige .exe + alle Abhaengigkeiten inkl. YOLOv8n-Gewichte,
; kein separates Python/pip-Setup und kein Download beim ersten Start noetig)
; in einen einzelnen Installer.
;
; Vor dem Bauen erst die .exe erzeugen:
;   .venv\Scripts\pyinstaller.exe --noconfirm VideoMotionDetektor.spec
;
; Dann bauen:
;   "C:\Program Files\Inno Setup 7\ISCC.exe" installer\VideoMotionDetektor.iss

#define AppName "Video Motion Detektor"
#define AppFolder "VideoMotionDetektor"
#define AppVersion "1.0.0"
#define AppPublisher "yakobo1970"
#define AppURL "https://www.undabtanzbar.de/software/"
#define AppExeName "VideoMotionDetektor.exe"

[Setup]
AppId={{6B0D8E57-3C1A-4F4E-9A52-7D2C1E8B4A93}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL=https://github.com/Yakobo1970/VideoMotionDetektor/releases
DefaultDirName={localappdata}\Programs\{#AppFolder}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile=..\assets\icon.ico
OutputDir=..\dist_installer
OutputBaseFilename={#AppFolder}-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
; Installiert pro Benutzer nach {localappdata} - keine Admin-Rechte noetig,
; passt zur App-Datenbank, die ohnehin schon dort liegt.
PrivilegesRequired=lowest
LicenseFile=..\LICENSE
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\{#AppFolder}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
