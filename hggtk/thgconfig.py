#
# Configuration dialog for TortoiseHg and Mercurial
#
# Copyright (C) 2007 Steve Borho <steve@borho.org>
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

import gtk
import gobject
import os
import pango
from mercurial import hg, ui, cmdutil, util
from dialog import error_dialog, question_dialog
from shlib import set_tortoise_icon
import iniparse

class ConfigDialog(gtk.Dialog):
    def __init__(self, root='', configrepo=False):
        """ Initialize the Dialog. """        
        gtk.Dialog.__init__(self, parent=None, flags=0,
                          buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))

        self.ui = ui.ui()
        try:
            repo = hg.repository(self.ui, path=root)
        except hg.RepoError:
            repo = None
            if configrepo:
                error_dialog('No repository found', 'Unable to configure')
                gtk.main_quit()

        if configrepo:
            self.ui = repo.ui
            self.rcpath = [os.sep.join([repo.root, '.hg', 'hgrc'])]
            self.set_title('TortoiseHg Configure Repository - ' + repo.root)
        else:
            self.rcpath = util.user_rcpath()
            self.set_title('TortoiseHg Configure User-Global Settings')

        #set_tortoise_icon(self, 'menurepobrowse.ico')
        self.ini = self.load_config(self.rcpath)

        self.connect('response', gtk.main_quit)
        # Create a new notebook, place the position of the tabs
        self.notebook = notebook = gtk.Notebook()
        notebook.set_tab_pos(gtk.POS_TOP)
        self.vbox.pack_start(notebook)
        notebook.show()
        self.show_tabs = True
        self.show_border = True

        self._btn_apply = gtk.Button("Apply")
        self._btn_apply.connect('clicked', self._apply_clicked)
        self.action_area.pack_end(self._btn_apply)

        self.pages = []
        self.history = {}
        #self.load_history()

        # create pages for each section of configuration file
        self._tortoise_info = (
                ('Commit Tool', 'tortoisehg.commit', ['qct', 'internal'],
                    'Select commit tool launched by TortoiseHg. Qct is' +
                    'not included, must be installed separately'),
                ('Revision Graph Viewer', 'tortoisehg.view', ['hgk', 'hgview'],
                    'Select revision graph (DAG) viewer launched by' +
                    'TortoiseHg'),
                ('Visual Diff Tool', 'tortoisehg.vdiff', [],
                    'Specify the visual diff tool; must be extdiff command'))
        self.tortoise_frame = self.add_page(notebook, 'TortoiseHG')
        self.fill_frame(self.tortoise_frame, self._tortoise_info)

        self.user_frame = self.add_page(notebook, 'User')
        self.paths_frame = self.add_page(notebook, 'Paths')
        self.web_frame = self.add_page(notebook, 'Web')
        self.email_frame = self.add_page(notebook, 'Email')
        self.hgmerge_frame = self.add_page(notebook, 'Merge')

        self.vbox.show_all()

    def fill_frame(self, frame, info):
        #tooltips = gtk.GtkTooltips()
        widgets = []
        vbox = gtk.VBox()
        frame.add(vbox)

        for label, cpath, values, tooltip in info:
            # Special case, add extdiff.cmd.* to values
            if cpath == 'tortoisehg.vdiff':
                for name, value in self.ui.configitems('extdiff'):
                    if name.startswith('cmd.'):
                        values.append(name[4:])

            vlist = gtk.ListStore(str)
            combo = gtk.ComboBoxEntry(vlist, 0)
            #tooltips.set_tip(combo, tooltip)
            widgets.append(combo)

            # Get currently configured value for this config level
            # using a ui.ui() will parse system wide and user configs.
            # using the repo.ui will _also_ parse the $root/.hg/hgrc
            section, key = cpath.split('.')
            curvalue = self.ui.config(section, key, None)

            vlist.append(['<unspecified>'])
            for v in values:
                vlist.append([v])
            if cpath in self.history:
                for v in self.history[cpath]:
                    vlist.append([v])

            if curvalue is None:
                combo.set_active(0)
            elif curvalue not in values:
                combo.set_active(values.index(curvalue))
            else:
                combo.get_child().set_text(curvalue)

            lbl = gtk.Label(label)
            hbox = gtk.HBox()
            hbox.pack_start(lbl, False, False, 4)
            hbox.pack_start(combo, True, True, 4)
            vbox.pack_start(hbox, False, False, 4)

        self.pages.append((frame, info, widgets))
        
        
    def load_config(self, rcpath):
        for fn in rcpath:
            if os.path.exists(fn):
                break
        else:
            fn = rcpath[0]
            f = open(fn, "w")
            f.write("# Generated by tortoisehg-config\n")
            f.close()
        return iniparse.INIConfig(file(fn))

    def add_page(self, notebook, tab):
        frame = gtk.Frame()
        frame.set_border_width(10)
        frame.set_size_request(500, 250)
        frame.show()

        label = gtk.Label(tab)
        notebook.append_page(frame, label)
        return frame

    def _apply_clicked(self, *args):
        pass
    
def run(root='', cmdline=[], **opts):
    dialog = ConfigDialog(root, configrepo='--configrepo' in cmdline)
    dialog.show_all()
    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or ''
    opts['cmdline'] = sys.argv
    run(**opts)
