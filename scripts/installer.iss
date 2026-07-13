#ifndef MyAppVersion
  #define MyAppVersion "1.0.1"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\MXHVideoEditor-1.0.1-Windows-x64"
#endif
[Setup]
AppId={{C9BC0D86-4EBA-42C5-AB33-DAB26463A528}
AppName=MXH Video Editor
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\MXH Video Editor
DefaultGroupName=MXH Video Editor
OutputDir=..\dist
OutputBaseFilename=MXHVideoEditor-{#MyAppVersion}-Setup
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\MXHVideoEditor.exe
[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\MXH Video Editor"; Filename: "{app}\MXHVideoEditor.exe"; Parameters: "gui"
Name: "{autodesktop}\MXH Video Editor"; Filename: "{app}\MXHVideoEditor.exe"; Parameters: "gui"; Tasks: desktopicon
[Tasks]
Name: desktopicon; Description: "Tạo biểu tượng trên màn hình"; GroupDescription: "Biểu tượng:"
[Run]
Filename: "{app}\MXHVideoEditor.exe"; Parameters: "gui"; Description: "Mở MXH Video Editor"; Flags: nowait postinstall skipifsilent
