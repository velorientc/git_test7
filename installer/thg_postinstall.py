# Post-install script for TortoiseHg Windows source installer
# Will run after all the file have been copied in place with '-install'
# and before files have been removed with '-uninstall'

import os, shutil, sys, subprocess

# Run tortoisehg.py script to register COM server and set registry key
scrpath = os.path.dirname(sys.argv[0])  # C:\Python25\Scripts
pyexe   = os.path.abspath(os.path.join(scrpath, '..', 'python.exe'))
thgpath = os.path.abspath(os.path.join(scrpath, '..', 'share', 'tortoisehg'))
scr     = os.path.join(thgpath, 'tortoisehg.py')

if sys.argv[1] == '-install':
    subprocess.call([pyexe, scr, '--register'])
    exe = os.path.join(scrpath, 'hg.exe')
    bat = os.path.join(scrpath, 'hg.bat')
    if os.path.exists(exe):
        tgt = os.path.join(thgpath, 'hg.exe')
        shutil.copy2(exe, tgt)
        file_created(tgt)
        exe = os.path.join(scrpath, 'hg-script.py')
        tgt = os.path.join(thgpath, 'hg-script.py')
        shutil.copy2(exe, tgt)
        file_created(tgt)
    elif os.path.exists(bat):
        tgt = os.path.join(thgpath, 'hg.bat')
        shutil.copy2(bat, tgt)
        file_created(tgt)
    print 'You must restart your machine for changes to take effect.'
elif sys.argv[1] == '-remove':
    subprocess.call([pyexe, scr, '--unregister'])
    print 'You must restart your machine to complete the uninstallation.'
