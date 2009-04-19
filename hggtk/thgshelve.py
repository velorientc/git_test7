#
# thgshelve.py - commit dialog for TortoiseHg
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
# Copyright (C) 2009 Steve Borho <steve@borho.org>
#

import os
import pygtk
import gtk
import cStringIO

from mercurial.i18n import _
from mercurial import ui, hg
from shlib import shell_notify
from gdialog import *
from status import *
from hgcmd import CmdDialog
from hglib import fromutf
import hgshelve

class GShelve(GStatus):
    """GTK+ based dialog for displaying repository status and shelving changes.

    Also provides related operations like add, delete, remove, revert, refresh,
    ignore, diff, and edit.
    """

    ### Overrides of base class methods ###

    def init(self):
        GStatus.init(self)
        self.mode = 'shelve'

    def parse_opts(self):
        GStatus.parse_opts(self)
        if not self.test_opt('rev'):
            self.opts['rev'] = ''

    def get_title(self):
        root = os.path.basename(self.repo.root)
        return ' '.join([root, 'shelve'])

    def get_icon(self):
        return 'shelve.ico'

    def auto_check(self):
        if self.test_opt('check'):
            for entry in self.filemodel : 
                if entry[FM_STATUS] in 'MAR':
                    entry[FM_CHECKED] = True
            self._update_check_count()


    def save_settings(self):
        settings = GStatus.save_settings(self)
        settings['gshelve'] = self._vpaned.get_position()
        return settings


    def load_settings(self, settings):
        GStatus.load_settings(self, settings)
        if settings:
            self._setting_vpos = settings['gshelve']
        else:
            self._setting_vpos = -1


    def get_tbbuttons(self):
        tbbuttons = GStatus.get_tbbuttons(self)
        tbbuttons.insert(2, gtk.SeparatorToolItem())
        self.shelve_btn = self.make_toolbutton(gtk.STOCK_FILE, _('Shelve'),
                self._shelve_clicked, tip=_('set aside selected changes'))
        self.unshelve_btn = self.make_toolbutton(gtk.STOCK_EDIT, _('Unshelve'),
                self._unshelve_clicked, tip=_('restore shelved changes'))
        tbbuttons.insert(2, self.unshelve_btn)
        tbbuttons.insert(2, self.shelve_btn)
        return tbbuttons

    def get_body(self):
        status_body = GStatus.get_body(self)
        vbox = gtk.VBox()  # For named shelf collection
        self._vpaned = gtk.VPaned()
        self._vpaned.add1(vbox)
        self._vpaned.add2(status_body)
        self._vpaned.set_position(self._setting_vpos)
        self._activate_shelve_buttons(True)
        return self._vpaned


    def get_menu_info(self):
        """
        Returns menu info in this order:
            merge, addrem, unknown, clean, ignored, deleted
        """
        merge, addrem, unknown, clean, ignored, deleted, unresolved, resolved \
                = GStatus.get_menu_info(self)
        return (merge + (('_shelve', self._shelve_file),),
                addrem + (('_shelve', self._shelve_file),),
                unknown + (('_shelve', self._shelve_file),),
                clean,
                ignored,
                deleted + (('_shelve', self._shelve_file),),
                unresolved,
                resolved,
               )


    def should_live(self, widget=None, event=None):
        return False


    def reload_status(self):
        if not self._ready: return False
        success = GStatus.reload_status(self)
        return success

    ### End of overridable methods ###

    def _has_shelve_file(self):
        return os.path.exists(self.repo.join('shelve'))
        
    def _activate_shelve_buttons(self, status):
        if status:
            self.shelve_btn.set_sensitive(True)
            self.unshelve_btn.set_sensitive(self._has_shelve_file())
        else:
            self.shelve_btn.set_sensitive(False)
            self.unshelve_btn.set_sensitive(False)

    def _shelve_selected(self, file=None):
        # get list of hunks that have not been rejected
        chunks = self._shelve_chunks
        hlist = [x[DM_CHUNK_ID] for x in self.diff_model if not x[DM_REJECTED]]
        if file:
            hlist = [cid for cid in hlist if chunks[cid].filename() == file]
        if not hlist:
            Prompt(_('Shelve'), _('Please select diff chunks to shelve'),
                    self).run()
            return

        doforce = False
        doappend = False
        if self._has_shelve_file():
            from gtklib import MessageDialog
            dialog = MessageDialog(flags=gtk.DIALOG_MODAL)
            dialog.set_title(_('Shelve'))
            dialog.set_markup(_('<b>Shelve file exists!</b>'))
            dialog.add_buttons(_('Overwrite'), 1,
                               _('Append'), 2,
                               _('Cancel'), -1)
            dialog.set_transient_for(self)
            rval = dialog.run()
            dialog.destroy()
            if rval == 1:
                doforce = True
            elif rval == 2:
                doappend = True
            else:
                return

        # capture the selected hunks to shelve
        fc = []
        sc = []
        for n, c in enumerate(chunks):
            if isinstance(c, hgshelve.header):
                if len(fc) > 1 or (len(fc) == 1 and fc[0].binary()):
                    sc += fc
                fc = [c]
            elif n in hlist:
                fc.append(c)
        if len(fc) > 1 or (len(fc) == 1 and fc[0].binary()):
            sc += fc
                
        def filter_patch(ui, chunks):
            return sc

        # shelve them!
        self.ui.interactive = True  # hgshelve only works 'interactively'
        opts = {'addremove': None, 'include': [], 'force': doforce,
                'append': doappend, 'exclude': []}
        hgshelve.filterpatch = filter_patch
        hgshelve.shelve(self.ui, self.repo, **opts)
        self.reload_status()
        
    def _unshelve(self):
        opts = {'addremove': None, 'include': [], 'force': None,
                'append': None, 'exclude': [], 'inspect': None}
        try:
            self.ui.quiet = True
            hgshelve.unshelve(self.ui, self.repo, **opts)
            self.ui.quiet = False
            self.reload_status()
        except:
            pass

    def _shelve_clicked(self, toolbutton, data=None):
        self._shelve_selected()
        self._activate_shelve_buttons(True)

    def _unshelve_clicked(self, toolbutton, data=None):
        self._unshelve()
        self._activate_shelve_buttons(True)

    def _shelve_file(self, stat, file):
        self._shelve_selected(file)
        self._activate_shelve_buttons(True)
        return True


def launch(root='', files=[], cwd='', main=True):
    u = ui.ui()
    u.updateopts(debug=False, traceback=False)
    repo = hg.repository(u, path=root)
    
    cmdoptions = {
        'user':'', 'date':'',
        'modified':True, 'added':True, 'removed':True, 'deleted':True,
        'unknown':False, 'ignored':False, 
        'exclude':[], 'include':[],
        'check': True, 'git':False, 'logfile':'', 'addremove':False,
    }
    
    dialog = GShelve(u, repo, cwd, files, cmdoptions, main)
    dialog.display()
    return dialog
    
def run(root='', files=[], cwd='', **opts):
    # If no files or directories were selected, take current dir
    # TODO: Not clear if this is best; user may expect repo wide
    if not files and cwd:
        files = [cwd]
    if launch(root, files, cwd, True):
        gtk.gdk.threads_init()
        gtk.gdk.threads_enter()
        gtk.main()
        gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    from hglib import rootpath

    opts = {}
    opts['cwd'] = len(sys.argv) > 1 and sys.argv[1] or os.getcwd()
    opts['root'] = rootpath(opts['cwd'])
    run(**opts)
