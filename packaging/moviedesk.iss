; Inno Setup: baut aus der PyInstaller-Ausgabe einen Windows-Installer.
;
; Aufruf (der Workflow macht das selbst):
;   iscc /DVersion=0.1.0 packaging\moviedesk.iss
;
; Bewusst eine Installation ohne Administratorrechte: sie landet unter
; %LOCALAPPDATA%. Das erspart die Nachfrage der Benutzerkontensteuerung,
; die bei einer unsignierten Datei ohnehin nach dem Herausgeber fragt und
; "Unbekannt" anzeigt.

#ifndef Version
  #define Version "0.0.0"
#endif

#define AppName "MovieDesk"
#define AppPublisher "MovieDesk"
#define AppURL "https://github.com/aaaaaprvdgrwwelt/moviedesk"

[Setup]
AppId={{5A9C3E12-7B48-4A1F-9C6D-3E8F2A0B4D71}
AppName={#AppName}
AppVersion={#Version}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=MovieDesk-{#Version}-Windows-Setup
SetupIconFile=moviedesk.ico
UninstallDisplayIcon={app}\MovieDesk.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "deutsch"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
  GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\MovieDesk\*"; DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\MovieDesk.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\MovieDesk.exe"; \
  Tasks: desktopicon

[Run]
Filename: "{app}\MovieDesk.exe"; \
  Description: "{cm:LaunchProgram,{#AppName}}"; \
  Flags: nowait postinstall skipifsilent
