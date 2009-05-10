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

[Files]
Source: contrib\mercurial.el; DestDir: {app}/contrib
Source: contrib\vim\*.*; DestDir: {app}/contrib/vim
Source: contrib\zsh_completion; DestDir: {app}/contrib
Source: contrib\hgk; DestDir: {app}/contrib
Source: contrib\win32\ReadMe.html; DestDir: {app}; Flags: isreadme
Source: {app}\Mercurial.ini; DestDir: {app}\backup; Flags: external skipifsourcedoesntexist uninsneveruninstall
Source: contrib\win32\mercurial.ini; DestDir: {app}; DestName: Mercurial.ini; AfterInstall: FileExpandString('{app}\Mercurial.ini')
Source: ReleaseNotes.txt; DestDir: {app}; DestName: ReleaseNotes.txt
Source: ..\contrib\*.exe; DestDir: {app}; Flags: ignoreversion restartreplace uninsrestartdelete
Source: ..\contrib\TortoiseOverlays\*.*; DestDir: {app}/TortoiseOverlays;
Source: dist\*.exe; DestDir: {app}; Flags: ignoreversion restartreplace uninsrestartdelete
Source: dist\*.dll; DestDir: {app}; Flags: ignoreversion restartreplace uninsrestartdelete
Source: dist\library.zip; DestDir: {app}
Source: doc\*.html; DestDir: {app}\docs
Source: icons\*; DestDir: {app}\icons; Flags: ignoreversion recursesubdirs createallsubdirs
Source: dist\share\*; DestDir: {app}\share; Flags: ignoreversion recursesubdirs createallsubdirs
Source: dist\lib\*; DestDir: {app}\lib; Flags: ignoreversion recursesubdirs createallsubdirs
Source: dist\etc\*; DestDir: {app}\etc; Flags: ignoreversion recursesubdirs createallsubdirs
Source: templates\*.*; DestDir: {app}\templates; Flags: recursesubdirs createallsubdirs
Source: locale\*.*; DestDir: {app}\locale; Flags: recursesubdirs createallsubdirs
Source: i18n\*.*; DestDir: {app}\i18n; Flags:
Source: CONTRIBUTORS; DestDir: {app}; DestName: Contributors.txt
Source: COPYING.txt; DestDir: {app}; DestName: Copying.txt
Source: ..\icons\hgicon.ico; DestDir: {app}
Source: ..\files\gtkrc; DestDir: {app}\etc\gtk-2.0; AfterInstall: EditOptions()

[INI]
Filename: {app}\Mercurial.url; Section: InternetShortcut; Key: URL; String: http://www.selenic.com/mercurial/
Filename: {app}\TortoiseHg.url; Section: InternetShortcut; Key: URL; String: http://bitbucket.org/tortoisehg/stable/

[Icons]
Name: {group}\TortoiseHg Web Site; Filename: {app}\TortoiseHg.url
Name: {group}\Mercurial Web Site; Filename: {app}\Mercurial.url
Name: {group}\Mercurial Command Reference; Filename: {app}\docs\hg.1.html
Name: {group}\Uninstall TortoiseHg; Filename: {uninstallexe}

[Run]
Filename: {app}\add_path.exe; Parameters: {app}; StatusMsg: Adding the installation path to the search path...
Filename: msiexec.exe; Parameters: "/i ""{app}\TortoiseOverlays\TortoiseOverlays-1.0.4.11886-win32.msi"" /qn /norestart ALLUSERS=1"; StatusMsg: Installing TortoiseOverlays.dll ...
Filename: regsvr32.exe; Parameters: "/s ""{app}\THgShell.dll"""; StatusMsg: Installing shell extension...

[UninstallRun]
Filename: {app}\add_path.exe; Parameters: /del {app}
Filename: regsvr32.exe; Parameters: "/s /u ""{app}\THgShell.dll"""

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

var ThemePage: TInputOptionWizardPage;
var IsUpgrade: Boolean;

procedure InitializeWizard;
begin
  ThemePage := CreateInputOptionPage(wpSelectComponents,
    'Theme Selection', '',
    'Please select a theme, then click Next.',
    True, False);
  ThemePage.Add('Neutrino (recommended, especially on Vista)');
  ThemePage.Add('Brushed');
  ThemePage.Add('Blue-Steel');
  ThemePage.Add('MS-Windows (original)');

  case GetPreviousData('Theme', '') of
    'Neutrino': ThemePage.SelectedValueIndex := 0;
    'Brushed': ThemePage.SelectedValueIndex := 1;
    'Blue-Steel': ThemePage.SelectedValueIndex := 2;
    'MS-Windows': ThemePage.SelectedValueIndex := 3;
  else
    ThemePage.SelectedValueIndex := 0;
  end;
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
var
  Theme: String;
begin
  { Store the settings so we can restore them next time }
  case ThemePage.SelectedValueIndex of
    0: Theme := 'Neutrino';
    1: Theme := 'Brushed';
    2: Theme := 'Blue-Steel';
    3: Theme := 'MS-Windows';
  end;
  SetPreviousData(PreviousDataKey, 'Theme', Theme);
end;

procedure SetCommentMarker(var lines: TArrayOfString; option: String; selected: boolean);
var
  i : integer;
begin
  if selected then exit;
  for i := 0 to pred(GetArrayLength(lines)) do
    if pos(option, lines[i]) > 0 then 
    begin
        lines[i][1] := '#';
    end;
end;

procedure EditOptions();
var
  lines : TArrayOfString;
  filename : String;
begin
  filename := ExpandConstant(CurrentFilename);
  LoadStringsFromFile(filename, lines);
  
  SetCommentMarker(lines, 'gtk-theme-name = "Neutrino"', ThemePage.SelectedValueIndex = 0);
  SetCommentMarker(lines, 'gtk-theme-name = "Brushed"', ThemePage.SelectedValueIndex = 1);
  SetCommentMarker(lines, 'gtk-theme-name = "Blue-Steel"', ThemePage.SelectedValueIndex = 2);
  SetCommentMarker(lines, 'gtk-theme-name = "MS-Windows"', ThemePage.SelectedValueIndex = 3);
  
  SaveStringsToFile(filename, lines, False);
end;

function InitializeSetup(): Boolean;
var
 ThgSwReg: String;
 CRLF: String;
 msg: String;
begin
 CRLF := chr(10) + chr(13);
 Result := True;

 {abort installation if TortoiseHg 0.4 or earlier is installed}
 if RegQueryStringValue(HKLM, 'Software\TortoiseHg', '', ThgSwReg) then
 begin
  IsUpgrade := True;
  {if old shell extensions are found, force uninstall and reboot}
  if (FileExists(ThgSwReg + '\tortoisehg.dll')) then
  begin
    msg := 'TortoiseHg Setup Error:' + CRLF + CRLF +
      'The version of TortoiseHg installed is too old to upgrade in place.' + CRLF +
      'You must uninstall it before installing this version.' + CRLF + CRLF +
      'Please uninstall the existing version, then run the installer again ' +
      'to continue.';
    MsgBox(msg, mbError, MB_OK);
    Result := False; {quit and abort installation}
  end else begin
    msg := 'Your current site-wide Mercurial.ini will be copied into' + CRLF +
           ThgSwReg + '\backup' + CRLF +
           'After install you may merge changes back into the new Mercurial.ini'
    MsgBox(msg, mbInformation, MB_OK);
  end;
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
