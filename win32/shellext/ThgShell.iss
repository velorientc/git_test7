[Setup]
AppCopyright=Copyright 2007 TK Soh and others
AppName=TortoiseHg
AppVerName=TortoiseHg snapshot
;InfoAfterFile=iss/postinstall.txt
;LicenseFile=COPYING.txt
ShowLanguageDialog=yes
AppPublisher=TK Soh and others
AppPublisherURL=http://tortoisehg.sourceforge.net/
AppSupportURL=http://tortoisehg.sourceforge.net/
AppUpdatesURL=http://tortoisehg.sourceforge.net/
AppID=TortoiseHg
AppContact=teekaysoh@gmail.com
OutputBaseFilename=THgShell_setup
DefaultDirName={sd}\TortoiseHg
;SourceDir=.
VersionInfoDescription=TortoiseHg
VersionInfoCopyright=Copyright 2007 TK Soh and others
VersionInfoCompany=TK Soh and others
InternalCompressLevel=max
SolidCompression=true
;SetupIconFile=icons\hg.ico
AllowNoIcons=true
DefaultGroupName=TortoiseHg
PrivilegesRequired=poweruser
;AlwaysRestart=yes
SetupLogging=yes

[Files]
Source: THgShell.dll; DestDir: {app}; Flags: ignoreversion
Source: ..\..\icons\*; DestDir: {app}\icons ; Flags: ignoreversion recursesubdirs createallsubdirs

#include "registry.iss"
