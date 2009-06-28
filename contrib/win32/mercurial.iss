; Script generated by the Inno Setup Script Wizard.
; SEE THE DOCUMENTATION FOR DETAILS ON CREATING INNO SETUP SCRIPT FILES!

[Setup]
AppCopyright=Copyright 2005-2009 Matt Mackall and others
AppName=TortoiseHg
AppVerName=TortoiseHg-0.8
InfoAfterFile=contrib/win32/postinstall.txt
LicenseFile=COPYING.txt
ShowLanguageDialog=yes
AppPublisher=Steve Borho and others
AppPublisherURL=http://bitbucket.org/tortoisehg/stable/
AppSupportURL=http://bitbucket.org/tortoisehg/stable/
AppUpdatesURL=http://bitbucket.org/tortoisehg/stable/
AppID=TortoiseHg
AppContact=teekaysoh@gmail.com
AppMutex=thgtaskbar,Global\thgtaskbar
OutputBaseFilename=TortoiseHg-0.8
DefaultDirName={pf}\TortoiseHg
SourceDir=..\..
VersionInfoDescription=Mercurial distributed SCM
VersionInfoCopyright=Copyright 2005-2009 Matt Mackall and others
VersionInfoCompany=Matt Mackall and others
InternalCompressLevel=max
SolidCompression=true
SetupIconFile=..\icons\hgicon.ico
UninstallDisplayIcon={app}\hgicon.ico
WizardImageFile=..\icons\install-wizard.bmp
WizardImageStretch=no
WizardImageBackColor=$ffffff
WizardSmallImageFile=..\icons\install-wizard-small.bmp
AllowNoIcons=true
DefaultGroupName=TortoiseHg
PrivilegesRequired=poweruser
AlwaysRestart=yes
SetupLogging=yes
ArchitecturesInstallIn64BitMode=x64

[Files]
Source: contrib\mercurial.el; DestDir: {app}/contrib
Source: contrib\refreshicons.cmd; DestDir: {app}/contrib
Source: contrib\vim\*.*; DestDir: {app}/contrib/vim
Source: contrib\zsh_completion; DestDir: {app}/contrib
Source: contrib\hgk; DestDir: {app}/contrib
Source: contrib\win32\ReadMe.html; DestDir: {app}; Flags: isreadme
Source: {app}\Mercurial.ini; DestDir: {app}\backup; Flags: external skipifsourcedoesntexist uninsneveruninstall
Source: contrib\win32\mercurial.ini; DestDir: {app}; DestName: Mercurial.ini; AfterInstall: FileExpandString('{app}\Mercurial.ini')
Source: ReleaseNotes.txt; DestDir: {app}; DestName: ReleaseNotes.txt
Source: ..\contrib\*.exe; DestDir: {app}; Flags: ignoreversion restartreplace uninsrestartdelete
Source: ..\contrib\*.dll; DestDir: {app}; Flags: ignoreversion restartreplace uninsrestartdelete
Source: ..\contrib\TortoiseOverlays\*.*; DestDir: {app}/TortoiseOverlays;
Source: dist\*.exe; DestDir: {app}; Flags: ignoreversion restartreplace uninsrestartdelete
Source: dist\*.dll; DestDir: {app}; Flags: ignoreversion restartreplace uninsrestartdelete
Source: dist\library.zip; DestDir: {app}
Source: doc\*.html; DestDir: {app}\docs
Source: icons\*; DestDir: {app}\icons; Flags: ignoreversion recursesubdirs createallsubdirs
Source: dist\gtk\*; DestDir: {app}\gtk; Flags: ignoreversion recursesubdirs createallsubdirs
Source: templates\*.*; DestDir: {app}\templates; Flags: recursesubdirs createallsubdirs
Source: locale\*.*; DestDir: {app}\locale; Flags: recursesubdirs createallsubdirs
Source: i18n\*.*; DestDir: {app}\i18n; Flags:
Source: CONTRIBUTORS; DestDir: {app}; DestName: Contributors.txt
Source: COPYING.txt; DestDir: {app}; DestName: Copying.txt
Source: ..\icons\hgicon.ico; DestDir: {app}
Source: ..\contrib\vcredist_x86.exe; DestDir: {tmp}; Check: ShouldInstallVCPPSP1 and not Is64BitInstallMode
Source: ..\contrib\vcredist_x64.exe; DestDir: {tmp}; Check: ShouldInstallVCPPSP1 and Is64BitInstallMode

Source: ..\files\THgShellx86.dll; DestDir: {app}; DestName: ThgShell.dll; Check: not Is64BitInstallMode; Flags: ignoreversion restartreplace uninsrestartdelete
Source: ..\files\ThgShellx64.dll; DestDir: {app}; DestName: ThgShell.dll; Check: Is64BitInstallMode; Flags: ignoreversion restartreplace uninsrestartdelete

[INI]
Filename: {app}\Mercurial.url; Section: InternetShortcut; Key: URL; String: http://www.selenic.com/mercurial/
Filename: {app}\TortoiseHg.url; Section: InternetShortcut; Key: URL; String: http://bitbucket.org/tortoisehg/stable/

[Icons]
Name: {group}\TortoiseHg Web Site; Filename: {app}\TortoiseHg.url
Name: {group}\Mercurial Web Site; Filename: {app}\Mercurial.url
Name: {group}\Mercurial Command Reference; Filename: {app}\docs\hg.1.html
Name: {group}\Uninstall TortoiseHg; Filename: {uninstallexe}

[Run]
Filename: {tmp}\vcredist_x86.exe; Parameters: /q; Check: ShouldInstallVCPPSP1 and not Is64BitInstallMode
Filename: {tmp}\vcredist_x64.exe; Parameters: /q; Check: ShouldInstallVCPPSP1 and Is64BitInstallMode
Filename: {app}\add_path.exe; Parameters: {app}; StatusMsg: Adding the installation path to the search path...
Filename: msiexec.exe; Parameters: "/i ""{app}\TortoiseOverlays\TortoiseOverlays-1.0.6.16523-win32.msi"" /qn /norestart ALLUSERS=1"; Check: not Is64BitInstallMode; StatusMsg: Installing TortoiseOverlays.dll ...
Filename: msiexec.exe; Parameters: "/i ""{app}\TortoiseOverlays\TortoiseOverlays-1.0.6.16523-x64.msi"" /qn /norestart ALLUSERS=1"; Check: Is64BitInstallMode; StatusMsg: Installing TortoiseOverlays.dll ...

[UninstallRun]
Filename: {app}\add_path.exe; Parameters: /del {app}

[UninstallDelete]
Type: files; Name: {app}\Mercurial.url
Type: files; Name: {app}\TortoiseHg.url

[Registry]
Root: HKLM; Subkey: Software\TortoiseHg; Flags: uninsdeletekey; ValueData: {app}
Root: HKLM; Subkey: Software\Mercurial; Flags: uninsdeletekey; ValueData: {app}\Mercurial.ini

[Code]
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
var SP1Missing: Boolean;

function ShouldInstallVCPPSP1(): Boolean;
begin
    Result := SP1Missing;
end;

function InitializeSetup(): Boolean;
var
 ThgSwReg: String;
 msg: String;
 CRLF: String;
begin
 CRLF := chr(10) + chr(13);
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

 {Detect whether VC2005-SP1 Redistributable package is installed}
 if (not(RegValueExists(HKLM, 'SOFTWARE\Microsoft\NET Framework Setup\NDP\v2.0.50727', 'SP'))) then
    SP1Missing := True;
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

#include "registry.iss"
