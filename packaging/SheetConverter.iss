; Inno Setup recipe: makes RunSpriteRunSheetConverter_Setup_v<version>.exe from the PyInstaller folder
; dist\RunSpriteRunSheetConverter. Built on the PC by build_installer.bat:
;   ISCC /DAppVersion=<version> packaging\SheetConverter.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{0A0BC95F-0259-4E7E-B89B-644003B8B3D8}
AppName=RunSpriteRun Sheet Converter
AppVersion={#AppVersion}
AppVerName=RunSpriteRun Sheet Converter {#AppVersion}
AppPublisher=Harley Lehmann
; Per-user install: no administrator rights needed. When the Browse button picks a folder, Inno Setup adds the
; RunSpriteRunSheetConverter sub-folder to it (its default behaviour).
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\RunSpriteRunSheetConverter
DisableProgramGroupPage=yes
DefaultGroupName=RunSpriteRun Sheet Converter
OutputDir=..\dist_installer
OutputBaseFilename=RunSpriteRunSheetConverter_Setup_v{#AppVersion}
UninstallDisplayIcon={app}\RunSpriteRunSheetConverter.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Tasks]
Name: "startmenuicon"; Description: "Create a Start Menu shortcut"; GroupDescription: "Shortcuts:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\RunSpriteRunSheetConverter\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\README_CONVERTER.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\RunSpriteRun Sheet Converter"; Filename: "{app}\RunSpriteRunSheetConverter.exe"; Tasks: startmenuicon
Name: "{autoprograms}\RunSpriteRun Sheet Converter files"; Filename: "{app}"; Tasks: startmenuicon
Name: "{autodesktop}\RunSpriteRun Sheet Converter"; Filename: "{app}\RunSpriteRunSheetConverter.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\RunSpriteRunSheetConverter.exe"; Description: "Start RunSpriteRun Sheet Converter"; Flags: nowait postinstall skipifsilent

[Code]
function StartsWith(const Text, Prefix: String): Boolean;
begin
  Result := (Prefix <> '') and (CompareText(Copy(Text, 1, Length(Prefix)), Prefix) = 0);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Dir: String;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    Dir := WizardDirValue;
    if StartsWith(Dir, ExpandConstant('{commonpf}')) or StartsWith(Dir, ExpandConstant('{commonpf32}')) or
       StartsWith(Dir, ExpandConstant('{win}')) then
    begin
      MsgBox('Windows does not let the Sheet Converter save your work in this folder. Please choose another ' +
             'folder, for example one under your user folder.', mbInformation, MB_OK);
      Result := False;
    end;
  end;
end;
