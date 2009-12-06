; Script generated by the Inno Setup Script Wizard.
; SEE THE DOCUMENTATION FOR DETAILS ON CREATING INNO SETUP SCRIPT FILES!

#ifndef VERSION
#define VERSION "snapshot"
#endif

[Setup]
AppCopyright=Copyright 2005-2009 Matt Mackall and others
AppName=TortoiseHg
AppVerName=TortoiseHg {#VERSION}
InfoAfterFile=contrib/win32/postinstall.txt
LicenseFile=COPYING.txt
ShowLanguageDialog=yes
AppPublisher=Steve Borho and others
AppPublisherURL=http://tortoisehg.org/
AppSupportURL=http://tortoisehg.org/
AppUpdatesURL=http://tortoisehg.org/
AppID=TortoiseHg
AppContact=Steve Borho <steve@borho.org>
OutputBaseFilename=TortoiseHg-{#VERSION}
DefaultDirName={pf}\TortoiseHg
SourceDir=..\..
VersionInfoDescription=Mercurial distributed SCM
VersionInfoCopyright=Copyright 2005-2009 Matt Mackall and others
VersionInfoCompany=Matt Mackall and others
InternalCompressLevel=max
SolidCompression=true
SetupIconFile=icons\thg_logo.ico
UninstallDisplayIcon={app}\thg_logo.ico
WizardImageFile=..\misc\install-wizard.bmp
WizardImageStretch=no
WizardImageBackColor=$ffffff
WizardSmallImageFile=..\misc\install-wizard-small.bmp
AllowNoIcons=true
DefaultGroupName=TortoiseHg
PrivilegesRequired=poweruser
AlwaysRestart=no
SetupLogging=yes
ArchitecturesInstallIn64BitMode=x64

[Types]
Name: full; Description: Full installation
Name: custom; Description: Custom installation; Flags: iscustom

[Components]
Name: main; Description: Main Files (includes 'hg' and 'hgtk' commands); Types: full custom; Flags: fixed
Name: help; Description: Help Files; Types: full
Name: hgbook; Description: The book 'Mercurial: The Definitive Guide' (PDF); Types: full
Name: shell; Description: Shell integration (overlay icons, context menu) [admin required]; Types: full; Flags: restart; Check: ShellInstallPossible

[Files]
Source: ..\build-hg\contrib\mercurial.el; DestDir: {app}\contrib
Source: ..\build-hg\contrib\vim\*.*; DestDir: {app}\contrib\vim
Source: ..\build-hg\contrib\zsh\*.*; DestDir: {app}\contrib\zsh
Source: ..\build-hg\contrib\bash\*.*; DestDir: {app}\contrib\bash
Source: ..\build-hg\contrib\hgk; DestDir: {app}/contrib
Source: ..\build-hg\contrib\win32\ReadMe.html; DestDir: {app}; Flags: isreadme
Source: ..\build-hg\mercurial\templates\*.*; DestDir: {app}\templates; Flags: recursesubdirs createallsubdirs
Source: ..\build-hg\mercurial\help\*.txt; DestDir: {app}\help; Components: help
Source: ..\build-hg\mercurial\locale\*.*; DestDir: {app}\locale; Flags: recursesubdirs createallsubdirs
Source: ..\build-hg\i18n\*.*; DestDir: {app}\i18n
Source: ..\build-hg\doc\*.html; DestDir: {app}\docs; Flags: ignoreversion; Components: help
Source: ..\build-hg\doc\style.css; DestDir: {app}\docs; Flags: ignoreversion; Components: help
Source: {app}\Mercurial.ini; DestDir: {app}\backup; Flags: external skipifsourcedoesntexist uninsneveruninstall
Source: contrib\win32\mercurial.ini; DestDir: {app}; DestName: Mercurial.ini; AfterInstall: FileExpandString('{app}\Mercurial.ini')
Source: contrib\win32\mercurialuser.ini; DestDir: {%USERPROFILE}; DestName: Mercurial.ini; AfterInstall: FileExpandStringEx('{%USERPROFILE}\Mercurial.ini'); Flags: onlyifdoesntexist 
Source: ReleaseNotes.txt; DestDir: {app}; DestName: ReleaseNotes.txt
Source: ..\contrib\*.exe; DestDir: {app}
Source: ..\contrib\*.dll; DestDir: {app}
Source: ..\contrib\TortoiseOverlays\*.*; DestDir: {app}/TortoiseOverlays
Source: contrib\refreshicons.cmd; DestDir: {app}/contrib
Source: dist\*.exe; Excludes: thgtaskbar.exe; DestDir: {app}; Flags: ignoreversion
Source: dist\thgtaskbar.exe; DestDir: {app}; Flags: ignoreversion; Components: shell
Source: dist\*.dll; DestDir: {app}; Flags: ignoreversion
Source: dist\library.zip; DestDir: {app}
Source: doc\build\pdf\*.pdf; DestDir: {app}/docs; Flags: ignoreversion; Components: help
Source: doc\build\chm\*.chm; DestDir: {app}/docs; Flags: ignoreversion; Components: help
Source: icons\*; DestDir: {app}\icons; Flags: ignoreversion recursesubdirs createallsubdirs
Source: dist\gtk\*; DestDir: {app}\gtk; Flags: ignoreversion recursesubdirs createallsubdirs
Source: locale\*.*; DestDir: {app}\locale; Flags: recursesubdirs createallsubdirs
Source: i18n\*.*; DestDir: {app}\i18n; Flags: recursesubdirs createallsubdirs
Source: win32\*.reg; DestDir: {app}\cmenu_i18n
Source: COPYING.txt; DestDir: {app}; DestName: Copying.txt
Source: icons\thg_logo.ico; DestDir: {app}
Source: ..\misc\hgbook.pdf; DestDir: {app}/docs; Flags: ignoreversion; Components: hgbook
Source: ..\misc\ThgShellx86.dll; DestDir: {app}; DestName: ThgShell.dll; Check: not Is64BitInstallMode; Flags: ignoreversion restartreplace uninsrestartdelete; Components: shell
Source: ..\misc\ThgShellx86.dll; DestDir: {app}; DestName: ThgShellx86.dll; Check: Is64BitInstallMode; Flags: ignoreversion restartreplace uninsrestartdelete; Components: shell
Source: ..\misc\ThgShellx64.dll; DestDir: {app}; DestName: ThgShell.dll; Check: Is64BitInstallMode; Flags: ignoreversion restartreplace uninsrestartdelete; Components: shell

[INI]
Filename: {app}\Mercurial.url; Section: InternetShortcut; Key: URL; String: http://mercurial.selenic.com/
Filename: {app}\TortoiseHg.url; Section: InternetShortcut; Key: URL; String: http://tortoisehg.org/

[Icons]
Name: {group}\Start Taskbar App; Filename: {app}\thgtaskbar.exe; Components: shell
Name: {group}\TortoiseHg Book (chm); Filename: {app}\docs\TortoiseHg.chm; Components: help
Name: {group}\TortoiseHg Book (pdf); Filename: {app}\docs\TortoiseHg.pdf; Components: help
Name: {group}\TortoiseHg Web Site; Filename: {app}\TortoiseHg.url
Name: {group}\Mercurial Book; Filename: {app}\docs\hgbook.pdf; Components: hgbook
Name: {group}\Mercurial Command Reference; Filename: {app}\docs\hg.1.html; Components: help
Name: {group}\Mercurial Config Reference; Filename: {app}\docs\hgrc.5.html; Components: help
Name: {group}\Mercurial Web Site; Filename: {app}\Mercurial.url
Name: {group}\Uninstall TortoiseHg; Filename: {uninstallexe}

[Run]
Filename: {app}\add_path.exe; Parameters: {app}; StatusMsg: Adding the installation path to the search path...
Filename: msiexec.exe; Parameters: "/i ""{app}\TortoiseOverlays\TortoiseOverlays-1.0.6.16523-win32.msi"" /qn /norestart ALLUSERS=1"; Components: shell; StatusMsg: Installing TortoiseOverlays.dll ...
Filename: msiexec.exe; Parameters: "/i ""{app}\TortoiseOverlays\TortoiseOverlays-1.0.6.16523-x64.msi"" /qn /norestart ALLUSERS=1"; Check: Is64BitInstallMode; Components: shell; StatusMsg: Installing TortoiseOverlays.dll ...

[UninstallRun]
Filename: {app}\add_path.exe; Parameters: /del {app}

[UninstallDelete]
Type: files; Name: {app}\Mercurial.url
Type: files; Name: {app}\TortoiseHg.url

[Registry]
Root: HKLM; Subkey: Software\TortoiseHg; Flags: uninsdeletekey; ValueData: {app}
Root: HKLM; Subkey: Software\Mercurial; Flags: uninsdeletekey; ValueData: {app}\Mercurial.ini

[Code]
const
  wm_Close = $0010;

procedure FileExpandString(fn: String);
var
  InFile: String;
  i: Integer;
  InFileLines: TArrayOfString;
begin
  InFile := ExpandConstant(fn);
  LoadStringsFromFile(InFile, InFileLines);
  for i:= 0 to GetArrayLength(InFileLines)-1 do
    InFileLines[i] := ExpandConstant(InFileLines[i]);
  SaveStringsToFile(InFile, InFileLines, False);
end;

var IsUpgrade: Boolean;

function InitializeSetup(): Boolean;
var
 ThgSwReg: String;
 msg: String;
 CRLF: String;
begin
 CRLF := Chr(10) + Chr(13);
 Result := True;

 {abort installation if TortoiseHg 0.7 or earlier is installed}
 if RegQueryStringValue(HKLM, 'Software\TortoiseHg', '', ThgSwReg) then
 begin
  IsUpgrade := True;
  {hgproc was removed after 0.7, so it's a good guess}
  if (FileExists(ThgSwReg + '\hgproc.exe')) then
  begin
    msg := 'TortoiseHg Setup Error:' + CRLF + CRLF +
      'The version of TortoiseHg installed is too old to upgrade in place.' + CRLF +
      'You must uninstall it before installing this version.' + CRLF + CRLF +
      'Please uninstall the existing versions of TortoiseHg and TortoiseOverlays,' + CRLF +
      'then run the installer again to continue.';
    MsgBox(msg, mbError, MB_OK);
    Result := False; {quit and abort installation}
  end;
 end;
end;

var UserInfoPage: TInputQueryWizardPage;
var GetUserName: Boolean;

procedure InitializeWizard(); 
begin
  if (not(FileExists(ExpandConstant('{%USERPROFILE}\Mercurial.ini')))) then
  begin
    // Create the page
    UserInfoPage := CreateInputQueryPage(wpUserInfo,
      'Personal Information', 'Who are you?',
      'Please specify your name and email address, then click Next.');

    // Add items (False means it's not a password edit)
    UserInfoPage.Add('Full Name:', False);
    UserInfoPage.Add('Email address:', False);

    // Set initial values (optional)
    UserInfoPage.Values[0] := ExpandConstant('{username}');
    GetUserName := True;
  end
  else
    GetUserName := False;
end;

procedure FileExpandStringEx(fn: String);
var
  InFile: String;
  i: Integer;
  InFileLines: TArrayOfString;
begin
  if (GetUserName) then
  begin
    InFile := ExpandConstant(fn);
    LoadStringsFromFile(InFile, InFileLines);
    for i:= 0 to GetArrayLength(InFileLines)-1 do
    begin
      InFileLines[i] := ExpandConstantEx(InFileLines[i], 
        'hgusername', 
         UserInfoPage.Values[0] + ' <' + UserInfoPage.Values[1] + '>');
    end;
    SaveStringsToFile(InFile, InFileLines, False);
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  { Skip wpSelectDir page if upgrading; show all others }
  case PageID of
    wpSelectDir:
      Result := IsUpgrade;
  else
      Result := False;
  end;
end;

function TerminateThgTaskbar(): Boolean;
var
  TaskbarWindow: HWND;
  TaskbarMutex: String;
  tries: Integer;
begin
  { Terminate thgtaskbar.exe if it is running. Returns True, if successful }
  TaskbarMutex := 'thgtaskbar,Global\thgtaskbar';
  tries := 0;
  while (tries < 4) and CheckForMutexes(TaskbarMutex) do begin
    TaskbarWindow := FindWindowByWindowName('TortoiseHg Overlay Icon Server');
    if TaskbarWindow <> 0 then
      SendMessage(TaskbarWindow, wm_Close, 0, 0);
    TaskbarWindow := FindWindowByWindowName('TortoiseHg RPC server');
    if TaskbarWindow <> 0 then
      SendMessage(TaskbarWindow, wm_Close, 0, 0);
    Sleep(3000 { ms });
    tries := tries + 1;
  end;
  Result := not CheckForMutexes(TaskbarMutex);
end;

function PrepareToInstall: String;
begin
  if TerminateThgTaskbar() then
    Result := ''
  else
    Result := 'The installer failed to shut down thgtaskbar.exe, and will now close.';
end;

procedure CurUninstallStepChanged(step: TUninstallStep);
begin
  if step = usAppMutexCheck then
    TerminateThgTaskbar();
end;

function ShellInstallPossible(): Boolean;
begin
  if not IsAdminLoggedOn then begin
    SuppressibleMsgBox(
      'The shell integration install option (overlay icons, context menu) is unavailable (Administrator required)',
      mbInformation, MB_OK, 0
    );
    Result := False;
  end else Result := True;
end;

#include "registry.iss"
