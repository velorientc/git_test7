== C++ Shell Extension ==

=== Installing build tools ===

Get the gratis "Microsoft Windows SDK for Windows 7 and .NET Framework 3.5 SP1"
from microsoft.com.

You can install from web or download an ISO image, burn a DVD and install from
that. Make sure you get the correct download for the Windows version you want to
use for building: the x86 (32 bit) download won't install on 64 bit platforms.

The SDK contains the C++ compiler, linker, nmake, and header files, which is all
we need to build the x86 (32 bit) and 64 bit variants of the shell extension.

The compiler and linker can build both the 32 bit and the 64 bit targets, no matter
if you install the 32 bit (x86) or the 64 bit version of the SDK. In other words:
it can cross compile.

The SDK is compatible with Visual C++ 2005 and 2008 (including express versions).
But Visual C++ is *not* needed to build the shell extension!

Leave all install options at their defaults.

(see also C:\Program Files\Microsoft SDKs\Windows\v7.0\ReleaseNotes.Htm
section "4.4.2 Setting Build Environment Switches" after install)


=== Building the x86 (32 bit) target ===

Click on "Start -> All Programs -> Microsoft Windows SDK v7.0 -> CMD Shell"

This will open a command shell.

Copy/paste the following line (including the double quotes) into that shell

"C:\Program Files\Microsoft SDKs\Windows\v7.0\Bin\setenv.cmd" /xp /x86 /Release

and execute it (see ReleaseNotes.Htm).

This will show the following in your shell

'''
Setting SDK environment relative to C:\Program Files\Microsoft SDKs\Windows\v7.0.
Targeting Windows XP x86 RELEASE

C:\Program Files\Microsoft SDKs\Windows\v7.0>
'''

Then cd into the win32/shellext of the TortoiseHg sources and execute
  
  nmake /f Makefile.nmake clean
  
followed by

  nmake /f Makefile.nmake

Which should go like this:

'''
C:\Program Files\Microsoft SDKs\Windows\v7.0>cd C:\Users\adi\hgrepos\thg-stable\win32\shellext

C:\Users\adi\hgrepos\thg-stable\win32\shellext>nmake /f Makefile.nmake clean

Microsoft (R) Program Maintenance Utility Version 9.00.30729.01
Copyright (C) Microsoft Corporation.  All rights reserved.

        del *.obj *.dll *.exe *.lib *.exp *.manifest

C:\Users\adi\hgrepos\thg-stable\win32\shellext>nmake /f Makefile.nmake

Microsoft (R) Program Maintenance Utility Version 9.00.30729.01
Copyright (C) Microsoft Corporation.  All rights reserved.

        cl /nologo /Ox /W2 /EHsc /MT /DAPPMAIN /DTHG_DEBUG /c TortoiseUtils.cpp Direntry.cpp Directory.cpp Winstat.cpp ThgDebug.cpp
 InitStatus.cpp CShellExtCMenu.cpp CShellExtOverlay.cpp ShellExt.cpp StringUtils.cpp dirstate.cpp Winstat64.cpp Dirstatecache.cpp D
irectoryStatus.cpp Thgstatus.cpp QueryDirstate.cpp
TortoiseUtils.cpp
Direntry.cpp
Directory.cpp
Winstat.cpp
ThgDebug.cpp
InitStatus.cpp
CShellExtCMenu.cpp
CShellExtOverlay.cpp
ShellExt.cpp
StringUtils.cpp
dirstate.cpp
Winstat64.cpp
Dirstatecache.cpp
DirectoryStatus.cpp
Thgstatus.cpp
QueryDirstate.cpp
Generating Code...
        link /OUT:THgShell.dll /nologo /INCREMENTAL:NO /MANIFEST User32.lib Ole32.lib Shlwapi.lib Shell32.lib Advapi32.lib /DLL /DE
F:ShellExt.def TortoiseUtils.obj Direntry.obj Directory.obj Winstat.obj ThgDebug.obj InitStatus.obj CShellExtCMenu.obj CShellExtOve
rlay.obj ShellExt.obj StringUtils.obj dirstate.obj Winstat64.obj Dirstatecache.obj DirectoryStatus.obj Thgstatus.obj QueryDirstate.
obj
ShellExt.def(4) : warning LNK4017: DESCRIPTION statement not supported for the target platform; ignored
   Creating library THgShell.lib and object THgShell.exp
        mt -nologo -manifest THgShell.dll.manifest -outputresource:"THgShell.dll;#2"
        link /OUT:dirstate.exe /nologo /INCREMENTAL:NO /MANIFEST User32.lib Ole32.lib Shlwapi.lib Shell32.lib Advapi32.lib /SUBSYST
EM:CONSOLE dirstate.obj TortoiseUtils.obj Direntry.obj Directory.obj Winstat.obj ThgDebug.obj
        mt -nologo -manifest dirstate.exe.manifest -outputresource:"dirstate.exe;#1"
'''

This should produce the file THgShell.dll, which contains the 32 bit variant of the
shell extension.

To install it for testing on a 32 bit Windows, rename the THgShell.dll in "C:\Program Files\TortoiseHg"
to something else (e.g. THgShell-01.dll), then copy the newly built THgShell.dll to
"C:\Program Files\TortoiseHg" and restart explorer.exe (logout/login or restart will do as well).


=== Building the 64 bit target ===

Click on "Start -> All Programs -> Microsoft Windows SDK v7.0 -> CMD Shell"

This will open a command shell.

Copy/paste the following line (including the double quotes) into that shell

"C:\Program Files\Microsoft SDKs\Windows\v7.0\Bin\setenv.cmd" /xp /x64 /Release

and execute it (see ReleaseNotes.Htm).

This will show the following in your shell

'''
Setting SDK environment relative to C:\Program Files\Microsoft SDKs\Windows\v7.0.
Targeting Windows XP x64 RELEASE

C:\Program Files\Microsoft SDKs\Windows\v7.0>
'''

Then cd into the win32/shellext of the TortoiseHg sources and execute
  
  nmake /f Makefile.nmake clean
  
followed by

  nmake /f Makefile.nmake

Which should go like this:

'''
C:\Program Files\Microsoft SDKs\Windows\v7.0>cd C:\Users\adi\hgrepos\thg-stable\win32\shellext

C:\Users\adi\hgrepos\thg-stable\win32\shellext>nmake /f Makefile.nmake clean

Microsoft (R) Program Maintenance Utility Version 9.00.30729.01
Copyright (C) Microsoft Corporation.  All rights reserved.

        del *.obj *.dll *.exe *.lib *.exp *.manifest

C:\Users\adi\hgrepos\thg-stable\win32\shellext>nmake /f Makefile.nmake

Microsoft (R) Program Maintenance Utility Version 9.00.30729.01
Copyright (C) Microsoft Corporation.  All rights reserved.

        cl /nologo /Ox /W2 /EHsc /MT /DAPPMAIN /DTHG_DEBUG /c TortoiseUtils.cpp Direntry.cpp Directory.cpp Winstat.cpp ThgDebug.cpp
 InitStatus.cpp CShellExtCMenu.cpp CShellExtOverlay.cpp ShellExt.cpp StringUtils.cpp dirstate.cpp Winstat64.cpp Dirstatecache.cpp D
irectoryStatus.cpp Thgstatus.cpp QueryDirstate.cpp
TortoiseUtils.cpp
Direntry.cpp
Directory.cpp
Winstat.cpp
ThgDebug.cpp
InitStatus.cpp
CShellExtCMenu.cpp
CShellExtOverlay.cpp
ShellExt.cpp
StringUtils.cpp
dirstate.cpp
Winstat64.cpp
Dirstatecache.cpp
DirectoryStatus.cpp
Thgstatus.cpp
QueryDirstate.cpp
Generating Code...
        link /OUT:THgShell.dll /nologo /INCREMENTAL:NO /MANIFEST User32.lib Ole32.lib Shlwapi.lib Shell32.lib Advapi32.lib /DLL /DE
F:ShellExt.def TortoiseUtils.obj Direntry.obj Directory.obj Winstat.obj ThgDebug.obj InitStatus.obj CShellExtCMenu.obj CShellExtOve
rlay.obj ShellExt.obj StringUtils.obj dirstate.obj Winstat64.obj Dirstatecache.obj DirectoryStatus.obj Thgstatus.obj QueryDirstate.
obj
ShellExt.def(4) : warning LNK4017: DESCRIPTION statement not supported for the target platform; ignored
   Creating library THgShell.lib and object THgShell.exp
        mt -nologo -manifest THgShell.dll.manifest -outputresource:"THgShell.dll;#2"
        link /OUT:dirstate.exe /nologo /INCREMENTAL:NO /MANIFEST User32.lib Ole32.lib Shlwapi.lib Shell32.lib Advapi32.lib /SUBSYST
EM:CONSOLE dirstate.obj TortoiseUtils.obj Direntry.obj Directory.obj Winstat.obj ThgDebug.obj
        mt -nologo -manifest dirstate.exe.manifest -outputresource:"dirstate.exe;#1"
'''

This should produce the file THgShell.dll, which contains the 64 bit variant of the
shell extension.


=== Testing ===
The shell extension emits trace output (TDEBUG_TRACE macro calls in the sources). This output
can be captured by using for example the tool **DebugView** from Microsoft sysinternals (see 
http://technet.microsoft.com/en-us/sysinternals/bb896647.aspx).

The debug output must be enabled in the registry. Double click the file
"DebugShellExt.reg" and restart explorer.

Example output (copied via clipboard):

{{{
[3504] [THG] findHgRoot(W:\xxx2\aa): hgroot = 'W:\xxx2' (found repo)
[3504] [THG] Dirstatecache::get: lstat(W:\xxx2\.hg\dirstate) ok 
[3504] [THG] DirectoryStatus::read(W:\xxx2): done. 2 entries read
[3504] [THG] HgQueryDirstate: relbase = ''
[3504] [THG] HgQueryDirstate: basedir_status = M
}}}

Another very helpful tool is sysinternals **Autoruns** 
(http://technet.microsoft.com/en-us/sysinternals/bb963902.aspx ).
This can be used to explore the registration of the extension. Use the tab "Explorer"
to see the shell extensions registered.
Recommended setting is "Hide Microsoft Entries" in menu "Options"


=== TortoiseOverlays shim ===
The TortoiseHg shell extension uses the common TortoiseOverlays package shared with
other Tortoise projects (TortoiseSVN, TortoiseBZR, etc.).

The sources for the TortoiseOverlays project can be found at 
http://tortoisesvn.tigris.org/svn/tortoisesvn/TortoiseOverlays/
(use user: "guest", no password).


=== Issues ===
* #324 - Question mark overlays are missing on Windows 7
