# configure TortoiseHg shell extension settings

import os
import sys
import gtk

from tortoisehg.util.i18n import agettext as _
from tortoisehg.util import paths
from tortoisehg.hgtk import taskbarui
# import hgtk for signal setup side-effects
from tortoisehg.hgtk import hgtk

if hasattr(sys, "frozen"):
    # Insert PATH to binary installer gtk directory
    gtkpath = os.path.join(paths.bin_path, 'gtk')
    os.environ['PATH'] = os.pathsep.join([gtkpath, os.environ['PATH']])
    # Give stdout/stderr closed attributes to prevent ui.py errors
    sys.stdout.closed = True
    sys.stderr.closed = True

def main():
    dlg = taskbarui.TaskBarUI()
    dlg.show_all()
    dlg.connect('destroy', gtk.main_quit)
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__=='__main__':
    main()
