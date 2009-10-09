== C++ Shell Extension ==

<<toc>>

=== Compiling with Microsoft Visual C++ ===

Get the free Visual C++ Express 2008

Open a cmd.exe in directory "win32\shellext" and do the follwing

{{{
> "C:\Program Files\Microsoft Visual Studio 9.0\VC\vcvarsall.bat"
Setting environment for using Microsoft Visual Studio 2008 x86 tools.

> nmake /f Makefile.nmake

Microsoft (R) Program Maintenance Utility Version 9.00.30729.01
Copyright (C) Microsoft Corporation.  All rights reserved.

        cl /nologo /Ox /W2 /EHsc /MD /DAPPMAIN /DTHG_DEBUG /c TortoiseUtils.cpp Direntry.cpp
Directory.cpp Winstat.cpp ContextMenu.cpp IconOverlay.cpp ShellExt.cpp ShellUtils2.cpp
StringUtils.cpp dirstate.cpp Winstat64.cpp Dirstatecache.cpp DirectoryStatus.cpp Thgstatus.cpp
QueryDirstate.cpp
TortoiseUtils.cpp
Direntry.cpp
Directory.cpp
Winstat.cpp
ContextMenu.cpp
IconOverlay.cpp
ShellExt.cpp
ShellUtils2.cpp
StringUtils.cpp
dirstate.cpp
Winstat64.cpp
Dirstatecache.cpp
DirectoryStatus.cpp
Thgstatus.cpp
QueryDirstate.cpp
Generating Code...
        link /OUT:THgShell.dll /nologo /INCREMENTAL:NO /MANIFEST User32.lib Ole32.lib Shlwapi.lib
Shell32.lib Advapi32.lib /DLL /DEF:ShellExt.def TortoiseUtils.obj Direntry.obj Directory.obj Winstat.obj
ContextMenu.obj IconOverlay.obj ShellExt.obj ShellUtils2.obj StringUtils.obj dirstate.obj Winstat64.obj
Dirstatecache.obj DirectoryStatus.obj Thgstatus.obj QueryDirstate.obj
ShellExt.def(4) : warning LNK4017: DESCRIPTION statement not supported for the target platform; ignored
   Creating library THgShell.lib and object THgShell.exp
        mt -nologo -manifest THgShell.dll.manifest -outputresource:"THgShell.dll;#2"
        link /OUT:dirstate.exe /nologo /INCREMENTAL:NO /MANIFEST User32.lib Ole32.lib Shlwapi.lib
Shell32.lib Advapi32.lib /SUBSYSTEM:CONSOLE dirstate.obj
TortoiseUtils.obj Direntry.obj Directory.obj Winstat.obj
        mt -nologo -manifest dirstate.exe.manifest -outputresource:"dirstate.exe;#1"
}}}

This will build {{{THgShell.dll}}}.

To install it, rename the {{{THgShell.dll}}} in {{{C:\Program Files\TortoiseHg}}} to something else
(e.g. {{{THgShell-01.dll}}}), then copy the newly built {{{THgShell.dll}}} to
{{{C:\Program Files\TortoiseHg}}} and restart {{{explorer.exe}}} (logout/login or restart will
do as well).


==== Compiling with mingw32 =====

{{{
> set DEBUG=1

> make
g++ -DTHG_DEBUG   -c -o TortoiseUtils.o TortoiseUtils.cpp
g++ -DTHG_DEBUG   -c -o Direntry.o Direntry.cpp
g++ -DTHG_DEBUG   -c -o Directory.o Directory.cpp
g++ -DTHG_DEBUG   -c -o Winstat.o Winstat.cpp
g++ -DTHG_DEBUG   -c -o InitStatus.o InitStatus.cpp
g++ -DTHG_DEBUG   -c -o ContextMenu.o ContextMenu.cpp
g++ -DTHG_DEBUG   -c -o IconOverlay.o IconOverlay.cpp
g++ -DTHG_DEBUG   -c -o ShellExt.o ShellExt.cpp
g++ -DTHG_DEBUG   -c -o StringUtils.o StringUtils.cpp
g++ -DTHG_DEBUG   -c -o dirstate.o dirstate.cpp
g++ -DTHG_DEBUG   -c -o Winstat64.o Winstat64.cpp
g++ -DTHG_DEBUG   -c -o Dirstatecache.o Dirstatecache.cpp
g++ -DTHG_DEBUG   -c -o DirectoryStatus.o DirectoryStatus.cpp
g++ -DTHG_DEBUG   -c -o Thgstatus.o Thgstatus.cpp
g++ -DTHG_DEBUG   -c -o QueryDirstate.o QueryDirstate.cpp
g++ -o THgShell.dll TortoiseUtils.o Direntry.o Directory.o Winstat.o InitStatus.o ContextMenu.o IconOverlay.o ShellExt.o StringUtils.o dirstate.o Winstat64.o Dirstatecache.o DirectoryStatus.o Thgstatus.o QueryDirstate.o -s -lole32 -lshlwapi -luuid -L/lib -Wl,--subsystem,windows,--enable-stdcall-fixup,ShellExt.def -mwindows -shared
g++ -o dirstate.exe -DTHG_DEBUG -DAPPMAIN dirstate.cpp TortoiseUtils.o Direntry.o Directory.o Winstat.o -lole32 -lshlwapi -luuid -Wl,--subsystem,console,--enable-stdcall-fixup -mwindows
}}}


==== Compiling for 64 bit =====

 * The page "Visual C++ 2008 Express Edition And 64-Bit Targets" at 
http://jenshuebel.wordpress.com/2009/02/12/visual-c-2008-express-edition-and-64-bit-targets/
might be helpful. Express doesn't seem to support 64bit compilation out of the box

 * The page "How to: Enable a 64-Bit Visual C++ Toolset at the Command Line" in msdn at 
http://msdn.microsoft.com/en-us/library/x4d2c09s.aspx has some info how to use the
{{{Vcvarsall.bat}}} with options to select the different target platforms


With Visual C++ 2005 Professional, using 32bit crosscompiler for 64bit target:

{{{
> "C:\Program Files\Microsoft Visual Studio 8\VC\vcvarsall.bat" x86_amd64
Setting environment for using Microsoft Visual Studio 2005 x64 cross tools.

> nmake /f Makefile.nmake clean

Microsoft (R) Program Maintenance Utility Version 8.00.50727.762
Copyright (C) Microsoft Corporation.  All rights reserved.

        del *.obj *.dll *.exe *.lib *.exp *.manifest

> nmake /f Makefile.nmake

Microsoft (R) Program Maintenance Utility Version 8.00.50727.762
Copyright (C) Microsoft Corporation.  All rights reserved.

        cl /nologo /Ox /W2 /EHsc /MD /DAPPMAIN /DTHG_DEBUG /c TortoiseUtils.cpp Direntry.cpp
Directory.cpp Winstat.cpp ContextMenu.cpp IconOverlay.cpp ShellExt.cpp ShellUtils2.cpp
StringUtils.cpp dirstate.cpp Winstat64.cpp Dirstatecache.cpp DirectoryStatus.cpp
Thgstatus.cpp QueryDirstate.cpp
TortoiseUtils.cpp
Direntry.cpp
Directory.cpp
Winstat.cpp
ContextMenu.cpp
IconOverlay.cpp
ShellExt.cpp
ShellUtils2.cpp
StringUtils.cpp
dirstate.cpp
Winstat64.cpp
Dirstatecache.cpp
DirectoryStatus.cpp
Thgstatus.cpp
QueryDirstate.cpp
Generating Code...
        link /OUT:THgShell.dll /nologo /INCREMENTAL:NO /MANIFEST User32.lib Ole32.lib Shlwapi.lib
        Shell32.lib Advapi32.lib /DLL /DEF:ShellExt.def TortoiseUtils.obj Direntry.obj Directory.obj
        Winstat.obj ContextMenu.obj IconOverlay.obj ShellExt.obj ShellUtils2.obj StringUtils.obj
        dirstate.obj Winstat64.obj Dirstatecache.obj DirectoryStatus.obj Thgstatus.obj QueryDirstate.obj
ShellExt.def(4) : warning LNK4017: DESCRIPTION statement not supported for the target platform; ignored
   Creating library THgShell.lib and object THgShell.exp
        mt -nologo -manifest THgShell.dll.manifest -outputresource:"THgShell.dll;#2"
        link /OUT:dirstate.exe /nologo /INCREMENTAL:NO /MANIFEST User32.lib Ole32.lib Shlwapi.lib Shell32.lib Advapi32.lib /SUBSYSTEM:CONSOLE dirstate.obj
TortoiseUtils.obj Direntry.obj Directory.obj Winstat.obj
        mt -nologo -manifest dirstate.exe.manifest -outputresource:"dirstate.exe;#1"
}}}


=== Testing ===
The shell extension emits trace output (TDEBUG_TRACE macro calls in the sources). This output
can be captured by using for example the tool **DebugView** from Microsoft sysinternals (see 
http://technet.microsoft.com/en-us/sysinternals/bb896647.aspx).

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
The TortoiseHg shell extension relies on the common TortoiseOverlays package shared with
other Tortoise projects (TortoiseSVN, TortoiseBZR, etc.).

The sources for the TortoiseOverlays project seem to be at 
http://tortoisesvn.tigris.org/svn/tortoisesvn/TortoiseOverlays/ (use user: "guest", no password).


=== Issues ===
* #324 - Question mark overlays are missing on Windows 7
