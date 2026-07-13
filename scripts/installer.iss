#ifndef MyAppVersion
  #define MyAppVersion "0.5.3"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\MXHPublisher-0.5.3-Windows-x64"
#endif
[Setup]
AppId={{C9BC0D86-4EBA-42C5-AB33-DAB26463A528}
AppName=MXH Publisher
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\MXH Publisher
DefaultGroupName=MXH Publisher
OutputDir=..\dist
OutputBaseFilename=MXHPublisher-{#MyAppVersion}-Setup
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\MXHPublisher.exe
[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\MXH Publisher"; Filename: "{app}\MXHPublisher.exe"; Parameters: "gui"
Name: "{autodesktop}\MXH Publisher"; Filename: "{app}\MXHPublisher.exe"; Parameters: "gui"; Tasks: desktopicon
[Tasks]
Name: desktopicon; Description: "Tạo biểu tượng trên màn hình"; GroupDescription: "Biểu tượng:"
[Run]
Filename: "{app}\MXHPublisher.exe"; Parameters: "gui"; Description: "Mở MXH Publisher"; Flags: nowait postinstall skipifsilent
