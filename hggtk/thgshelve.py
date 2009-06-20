#
# thgshelve.py - commit dialog for TortoiseHg
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
# Copyright (C) 2009 Steve Borho <steve@borho.org>
#

import os
import gtk

from mercurial import util

from thgutil.i18n import _
from thgutil import hglib

from hggtk.status import GStatus, FM_STATUS, FM_CHECKED
from hggtk import hgshelve, gdialog, gtklib

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
        root = hglib.toutf(os.path.basename(self.repo.root))
        return ' '.join([root, 'shelve'])

    def get_icon(self):
        return 'shelve.ico'

    def auto_check(self):
        if self.test_opt('check'):
            for entry in self.filemodel:
                if entry[FM_STATUS] in 'MAR':
                    entry[FM_CHECKED] = True
            self.update_check_count()
        self.opts['check'] = False


    def save_settings(self):
        settings = GStatus.save_settings(self)
        settings['gshelve'] = self.vpaned.get_position()
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
                self.shelve_clicked, tip=_('set aside selected changes'))
        self.unshelve_btn = self.make_toolbutton(gtk.STOCK_EDIT, _('Unshelve'),
                self.unshelve_clicked, tip=_('restore shelved changes'))
        tbbuttons.insert(2, self.unshelve_btn)
        tbbuttons.insert(2, self.shelve_btn)
        return tbbuttons

    def get_body(self):
        status_body = GStatus.get_body(self)
        vbox = gtk.VBox()  # For named shelf collection
        self.vpaned = gtk.VPaned()
        self.vpaned.add1(vbox)
        self.vpaned.add2(status_body)
        self.vpaned.set_position(self._setting_vpos)
        self.activate_shelve_buttons(True)
        return self.vpaned


    def get_menu_info(self):
        """
        Returns menu info in this order:
            merge, addrem, unknown, clean, ignored, deleted
        """
        merge, addrem, unknown, clean, ignored, deleted, unresolved, resolved \
                = GStatus.get_menu_info(self)
        return (merge + ((_('_shelve'), self.shelve_file),),
                addrem + ((_('_shelve'), self.shelve_file),),
                unknown + ((_('_shelve'), self.shelve_file),),
                clean,
                ignored,
                deleted + ((_('_shelve'), self.shelve_file),),
                unresolved,
                resolved,
               )


    def should_live(self, widget=None, event=None):
        return False


    def reload_status(self):
        if not self.ready: return False
        success = GStatus.reload_status(self)
        self.activate_shelve_buttons(True)
        return success

    ### End of overridable methods ###

    def has_shelve_file(self):
        return os.path.exists(self.repo.join('shelve'))

    def activate_shelve_buttons(self, status):
        if status:
            self.shelve_btn.set_sensitive(len(self.filemodel) > 0)
            self.unshelve_btn.set_sensitive(self.has_shelve_file())
        else:
            self.shelve_btn.set_sensitive(False)
            self.unshelve_btn.set_sensitive(False)

    def shelve_selected(self, file=None):
        if len(self.filemodel) < 1:
            gdialog.Prompt(_('Shelve'),
                    _('No changes to shelve'), self).run()
            return

        wfiles = file and [file] or self.relevant_files('MAR')
        if not wfiles:
            gdialog.Prompt(_('Shelve'),
                    _('Please select diff chunks to shelve'), self).run()
            return

        doforce = False
        doappend = False
        if self.has_shelve_file():
            dialog = gtklib.MessageDialog(flags=gtk.DIALOG_MODAL)
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

        def filter_patch(ui, chunks):
            accepted = []
            for chunk in chunks:
                file = util.localpath(chunk.filename())
                if file not in wfiles:
                    # file was not selected for inclusion
                    continue
                if file not in self.filechunks:
                    # file was never filtered, accept all chunks
                    accepted.append(chunk)
                    continue
                schunks = self.filechunks[file]
                for i, c in enumerate(schunks):
                    if chunk != c:
                        continue
                    if i == 0 or c.active:
                        # take header and active chunks
                        accepted.append(chunk)
                    break
            return accepted

        # hgshelve only works 'interactively'
        self.ui.setconfig('ui', 'interactive', 'on')
        opts = {'addremove': None, 'include': [], 'force': doforce,
                'append': doappend, 'exclude': []}
        hgshelve.filterpatch = filter_patch
        # shelve them!
        hgshelve.shelve(self.ui, self.repo, **opts)
        self.opts['check'] = True  # recheck MAR after commit
        self.filechunks = {}       # do not keep chunks
        self.reload_status()

    def unshelve(self):
        opts = {'addremove': None, 'include': [], 'force': None,
                'append': None, 'exclude': [], 'inspect': None}
        try:
            self.ui.quiet = True
            hgshelve.unshelve(self.ui, self.repo, **opts)
            self.ui.quiet = False
            self.reload_status()
        except:
            pass

    def shelve_clicked(self, toolbutton, data=None):
        self.shelve_selected()
        self.activate_shelve_buttons(True)

    def unshelve_clicked(self, toolbutton, data=None):
        self.unshelve()
        self.activate_shelve_buttons(True)

    def shelve_file(self, stat, file):
        self.shelve_selected(file)
        self.activate_shelve_buttons(True)
        return True

def run(_ui, *pats, **opts):
    cmdoptions = {
        'user':opts.get('user', ''), 'date':opts.get('date', ''),
        'modified':True, 'added':True, 'removed':True, 'deleted':True,
        'unknown':True, 'ignored':False,
        'exclude':[], 'include':[],
        'check': True, 'git':False, 'addremove':False,
    }
    return GShelve(_ui, None, None, pats, cmdoptions)
