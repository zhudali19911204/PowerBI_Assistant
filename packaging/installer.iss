; Inno Setup script for Power BI 助手 — per-user install (no admin required).
; Must be saved as UTF-8 WITH BOM so the Chinese strings compile correctly on a GBK Windows.
; Build:   "ISCC.exe" installer.iss            (uses the default SrcDir below)
;     or:  "ISCC.exe" /DSrcDir="<bundle dir>" installer.iss
; SrcDir must point to the assembled bundle (the folder containing runtime\, powerbi_ai_assistant\,
; .streamlit\, packaging\, icon.ico). Output: C:\pbibuild\PowerBI助手_安装.exe

#ifndef SrcDir
  #define SrcDir "C:\pbibuild\PowerBI助手"
#endif
#define AppName "Power BI 助手"
#define AppVer "1.0.0"

[Setup]
AppName={#AppName}
AppVersion={#AppVer}
AppPublisher=ContiTech
DefaultDirName={localappdata}\PowerBI助手
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=C:\pbibuild
OutputBaseFilename=PowerBI助手_安装
Compression=lzma2/max
SolidCompression=yes
SetupIconFile={#SrcDir}\icon.ico
UninstallDisplayIcon={app}\icon.ico
WizardStyle=modern

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut / 创建桌面快捷方式"; GroupDescription: "Additional:"

[Files]
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

; Launch via wscript.exe EXPLICITLY so it works even when the .vbs file association was
; changed away from Windows Script Host (e.g. to Notepad by corporate policy).
[Icons]
Name: "{autoprograms}\Power BI 助手"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\packaging\启动.vbs"""; WorkingDir: "{app}\packaging"; IconFilename: "{app}\icon.ico"
Name: "{autoprograms}\卸载 Power BI 助手"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Power BI 助手"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\packaging\启动.vbs"""; WorkingDir: "{app}\packaging"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{sys}\wscript.exe"; Parameters: """{app}\packaging\启动.vbs"""; WorkingDir: "{app}\packaging"; Description: "Launch Power BI 助手 now"; Flags: nowait postinstall skipifsilent
