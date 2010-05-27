# thgshelve.py - commit dialog for TortoiseHg
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk

from mercurial import util, patch, ui

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, hgshelve

from tortoisehg.hgtk.status import GStatus, FM_STATUS, FM_CHECKED, FM_PATH
from tortoisehg.hgtk import gdialog, gtklib

class GShelve(GStatus):
    """GTK+ based dialog for displaying repository status and shelving changes.

    Also provides related operations like add, delete, remove, revert, refresh,
    ignore, diff, and edit.
    """

    ### Overrides of base class methods ###

    def init(self):
        GStatus.init(self)
        self.mode = 'shelve'
        self.ui = ErrBufUI(self.ui)

    def parse_opts(self):
        GStatus.parse_opts(self)
        if not self.test_opt('rev'):
            self.opts['rev'] = ''

    def get_title(self):
        return self.get_reponame() + ' - shelve'

    def get_icon(self):
        return 'shelve.ico'

    def auto_check(self):
        if not self.test_opt('check'):
            return
        for row in self.filemodel:
            if row[FM_STATUS] in 'MAR' and row[FM_PATH] not in self.excludes:
                row[FM_CHECKED] = True
        self.update_check_count()
        self.opts['check'] = False

    def save_settings(self):
        settings = GStatus.save_settings(self)
        #settings['gshelve'] = self.vpaned.get_position()
        return settings


    def load_settings(self, settings):
        GStatus.load_settings(self, settings)
        #if settings:
        #    self._setting_vpos = settings['gshelve']
        #else:
        #    self._setting_vpos = -1


    def get_tbbuttons(self):
        tbbuttons = GStatus.get_tbbuttons(self)
        tbbuttons.insert(0, gtk.SeparatorToolItem())
        self.shelve_btn = self.make_toolbutton(gtk.STOCK_FILE, _('Shelve'),
                self.shelve_clicked, tip=_('set aside selected changes'))
        self.unshelve_btn = self.make_toolbutton(gtk.STOCK_EDIT, _('Unshelve'),
                self.unshelve_clicked, tip=_('restore shelved changes'))
        self.abandon_btn = self.make_toolbutton(gtk.STOCK_CANCEL, _('Abandon'),
                self.abandon_clicked, tip=_('abandon shelved changes'))
        tbbuttons.insert(0, self.abandon_btn)
        tbbuttons.insert(0, self.unshelve_btn)
        tbbuttons.insert(0, self.shelve_btn)
        return tbbuttons

    def get_body(self):
        status_body = GStatus.get_body(self)
        #vbox = gtk.VBox()  # For named shelf collection
        #self.vpaned = gtk.VPaned()
        #self.vpaned.add1(vbox)
        #self.vpaned.add2(status_body)
        #self.vpaned.set_position(self._setting_vpos)
        self.activate_shelve_buttons(True)

        self.patch_text = gtk.TextView()
        self.patch_text.set_wrap_mode(gtk.WRAP_NONE)
        self.patch_text.set_editable(False)
        self.patch_text.modify_font(self.difffont)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC,
                            gtk.POLICY_AUTOMATIC)
        scroller.add(self.patch_text)
        self.diff_notebook.append_page(scroller, gtk.Label(_('Shelf Contents')))
        self.diff_notebook.show_all()
        return status_body

    def get_custom_menus(self):
        def shelve(menuitem, files):
            self.shelve_selected(files)
            self.activate_shelve_buttons(True)
        if self.is_merge():
            return ()
        else:
            return ((_('_Shelve'), shelve, 'MAR', 'shelve.ico'),)


    def should_live(self, widget=None, event=None):
        return False


    def refresh_complete(self):
        self.activate_shelve_buttons(True)
        if self.has_shelve_file():
            fp = open(self.repo.join('shelve'))
            buf = self.diff_highlight_buffer(fp.readlines())
            self.patch_text.set_buffer(buf)
        else:
            self.patch_text.set_buffer(gtk.TextBuffer())


    ### End of overridable methods ###

    def has_shelve_file(self):
        return os.path.exists(self.repo.join('shelve'))

    def activate_shelve_buttons(self, status):
        if status:
            self.shelve_btn.set_sensitive(len(self.filemodel) > 0)
            self.unshelve_btn.set_sensitive(self.has_shelve_file())
            self.abandon_btn.set_sensitive(self.has_shelve_file())
        else:
            self.shelve_btn.set_sensitive(False)
            self.unshelve_btn.set_sensitive(False)
            self.abandon_btn.set_sensitive(False)

    def shelve_selected(self, files=[]):
        if len(self.filemodel) < 1:
            gdialog.Prompt(_('Shelve'),
                    _('No changes to shelve'), self).run()
            return

        wfiles = files or self.relevant_checked_files('MAR')
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
                if file not in self.chunks:
                    # file was never filtered, accept all chunks
                    accepted.append(chunk)
                    continue
                schunks = self.chunks[file]
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
        self.ui.setconfig('ui', 'interactive', 'off')
        self.chunks.clear_filechunks() # do not keep chunks
        self.reload_status()

    def unshelve(self):
        opts = {'addremove': None, 'include': [], 'force': None,
                'append': None, 'exclude': [], 'inspect': None}
        try:
            self.ui.errorq = []
            self.ui.quiet = True
            hgshelve.unshelve(self.ui, self.repo, **opts)
            self.ui.quiet = False
            self.reload_status()
        except (util.Abort, IOError, patch.PatchError), e:
            gdialog.Prompt(_('Unshelve Abort'),
                           ''.join(self.ui.errorq), self).run()
        except Exception, e:
            gdialog.Prompt(_('Unshelve Error'),
                           _('Error: %s') % e, self).run()

    def abandon(self):
        try:
            response = gdialog.Confirm(_('Confirm Delete'), [], self,
                                       _('Delete the shelf contents?')).run()
            if response == gtk.RESPONSE_YES:
                self.ui.quiet = True
                hgshelve.abandon(self.ui, self.repo)
                self.ui.quiet = False
            self.reload_status()
        except Exception, e:
            gdialog.Prompt(_('Abandon Error'),
                    _('Error: %s') % e, self).run()

    def shelve_clicked(self, toolbutton, data=None):
        if not self.isuptodate():
            return
        self.shelve_selected()
        self.activate_shelve_buttons(True)

    def unshelve_clicked(self, toolbutton, data=None):
        if not self.isuptodate():
            return
        self.unshelve()
        self.activate_shelve_buttons(True)

    def abandon_clicked(self, toolbutton, data=None):
        if not self.isuptodate():
            return
        self.abandon()
        self.activate_shelve_buttons(True)

class ErrBufUI(ui.ui):
    """ui subclass to save hg and thg errors"""

    def __init__(self, src=None, errorq=[]):
        ui.ui.__init__(self, src)
        if src and hasattr(src, 'errorq'):
            self.errorq = src.errorq
        else:
            self.errorq = errorq

    def warn(self, *msg, **opts):
        self.errorq.extend(msg)
        ui.ui.warn(self, *msg, **opts)


def run(_ui, *pats, **opts):
    cmdoptions = {
        'user':opts.get('user', ''), 'date':opts.get('date', ''),
        'modified':True, 'added':True, 'removed':True, 'deleted':True,
        'unknown':True, 'ignored':False,
        'exclude':[], 'include':[],
        'check': True, 'git':False, 'addremove':False,
    }
    return GShelve(_ui, None, None, pats, cmdoptions)
