To use the shell extensions without building a full blown installer, you
must follow these steps (this presumes you have all of the dependencies
for hgtk, and can already run all of the dialogs.  See the crew wiki for
those details):

1) install mingw32
2) build this directory by running mingw32-make
3) copy contrib/hgtk.cmd to this directory and set hgtkpath as needed
4) install inno setup tool suite
5) open ThgShell.iss in the inno setup editor and run the script

This last step should create a "stub" install in C:\TortoiseHg.  It will
just have your ThgShell.dll (properly registered with explorer), and
the modified hgtk.cmd you copied into this directory.

Now restart explorer or reboot to use the new overlays and context
menus.

To remove the stub installer, run its unins00.exe.  You must do this
before trying to install another TortoiseHg installer, else hilarity
will ensue (ours, not yours).

See the crew wiki for debugging hints.

http://bitbucket.org/tortoisehg/crew/wiki/Home
