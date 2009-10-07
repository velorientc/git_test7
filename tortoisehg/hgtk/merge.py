# merge.py - TortoiseHg's dialog for merging revisions
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import gobject

from mercurial import hg, ui

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths

from tortoisehg.hgtk import changesetinfo, gtklib, commit, gdialog, hgcmd

RESPONSE_MERGE =  1
RESPONSE_COMMIT = 2
RESPONSE_UNDO =   3

MODE_NORMAL  = 'normal'
MODE_WORKING = 'working'

class MergeDialog(gtk.Dialog):
    """ Dialog to merge revisions of a Mercurial repo """
    def __init__(self, rev=None):
        """ Initialize the Dialog """
        gtk.Dialog.__init__(self)
        gtklib.set_tortoise_icon(self, 'menumerge.ico')
        gtklib.set_tortoise_keys(self)
        self.set_has_separator(False)
        self.set_resizable(False)
        self.connect('response', self.dialog_response)
        self.notify_func = None

        if not rev:
            gdialog.Prompt(_('Unable to merge'),
                           _('Must supply a target revision'), self).run()
            gobject.idle_add(self.destroy)
            return

        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
        except hglib.RepoError:
            gobject.idle_add(self.destroy)
            return
        self.set_title(_('Merging in %s') % hglib.get_reponame(repo))

        frame = gtk.Frame(_('Merge target (other)'))
        self.otherrev, desc = changesetinfo.changesetinfo(repo, rev, True)
        frame.add(desc)
        frame.set_border_width(5)
        self.vbox.pack_start(frame, False, False)
        self.otherframe = frame

        frame = gtk.Frame(_('Current revision (local)'))
        self.localrev, desc = changesetinfo.changesetinfo(repo, '.', True)
        frame.add(desc)
        frame.set_border_width(5)
        self.vbox.pack_start(frame, False, False)
        self.localframe = frame

        self.mergebtn = self.add_button(_('Merge'), RESPONSE_MERGE)
        self.commitbtn = self.add_button(_('Commit'), RESPONSE_COMMIT)
        self.undobtn = self.add_button(_('Undo'), RESPONSE_UNDO)
        self.closebtn = self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)

        vlist = gtk.ListStore(str,  # tool name
                              bool) # separator
        combo = gtk.ComboBoxEntry(vlist, 0)
        self.mergetool = combo
        combo.set_row_separator_func(lambda model, path: model[path][1])
        combo.child.set_width_chars(8)
        lbl = gtk.Label(_('Merge tools:'))
        lbl.set_alignment(1, 0.5)
        self.mergelabel = lbl
        self.action_area.add(lbl)
        self.action_area.add(combo)
        prev = False
        for tool in hglib.mergetools(repo.ui):
            cur = tool.startswith('internal:')
            vlist.append((hglib.toutf(tool), prev != cur))
            prev = cur
        mtool = repo.ui.config('ui', 'merge', None)
        if mtool:
            combo.child.set_text(hglib.toutf(mtool))
        else:
            combo.child.set_text('')

        # prepare to show
        self.mergebtn.grab_focus()
        self.commitbtn.set_sensitive(False)
        self.undobtn.set_sensitive(False)
        gobject.idle_add(self.after_init)

    def after_init(self):
        # CmdWidget
        self.cmd = hgcmd.CmdWidget()
        self.cmd.show_all()
        self.cmd.hide()
        self.vbox.pack_start(self.cmd, True, True, 6)

        # abort button
        self.abortbtn = self.add_button(_('Abort'), gtk.RESPONSE_CANCEL)
        self.abortbtn.hide()

    def dialog_response(self, dialog, response_id):
        def abort():
            self.cmd.stop()
            self.cmd.show_log()
            self.switch_to(MODE_NORMAL, cmd=False)
        # Merge button
        if response_id == RESPONSE_MERGE:
            self.domerge()
        # Commit button
        elif response_id == RESPONSE_COMMIT:
            self.docommit()
        # Undo button
        elif response_id == RESPONSE_UNDO:
            self.doundo()
        # Close button or dialog closing by the user
        elif response_id in (gtk.RESPONSE_CLOSE, gtk.RESPONSE_DELETE_EVENT):
            if self.cmd.is_alive():
                ret = gdialog.Confirm(_('Confirm Abort'), [], self,
                                      _('Do you want to abort?')).run()
                if ret == gtk.RESPONSE_YES:
                    abort()
            else:
                repo = hg.repository(ui.ui(), path=paths.find_root())
                if len(repo.parents()) == 2:
                    ret = gdialog.Confirm(_('Confirm Exit'), [], self,
                            _('To complete merging, you need to commit'
                              ' merged files in working directory.\n\n'
                              'Do you want to exit?')).run()
                    if ret == gtk.RESPONSE_YES:
                        self.destroy()
                        return # close dialog
                else:
                    self.destroy()
                    return # close dialog
        # Abort button
        elif response_id == gtk.RESPONSE_CANCEL:
            abort()
        else:
            raise _('unexpected response id: %s') % response_id

        self.run() # don't close dialog

    def set_notify_func(self, func, *args):
        self.notify_func = func
        self.notify_args = list(args)

    def switch_to(self, mode, cmd=True):
        if mode == MODE_NORMAL:
            normal = True
        elif mode == MODE_WORKING:
            normal = False
            self.abortbtn.grab_focus()
        else:
            raise _('unknown mode name: %s') % mode
        working = not normal

        self.otherframe.set_sensitive(normal)
        self.localframe.set_sensitive(normal)
        self.mergetool.set_property('visible', normal)
        self.mergelabel.set_property('visible', normal)
        self.mergebtn.set_property('visible', normal)
        self.commitbtn.set_property('visible', normal)
        self.undobtn.set_property('visible', normal)
        self.closebtn.set_property('visible', normal)
        if cmd:
            self.cmd.set_property('visible', working)
        self.abortbtn.set_property('visible', working)

    def cmd_done(self, returncode):
        self.switch_to(MODE_NORMAL, cmd=False)
        if returncode == 0 and not self.cmd.is_show_log():
            self.response(gtk.RESPONSE_CLOSE)

    def domerge(self):
        cmdline = ['hg', 'merge', '--rev', self.otherrev]
        tool = hglib.fromutf(self.mergetool.child.get_text())
        if tool:
            oldmergeenv = os.environ.get('HGMERGE')
            os.environ['HGMERGE'] = tool

        def cmd_done(returncode):
            self.switch_to(MODE_NORMAL, cmd=False)
            repo = hg.repository(ui.ui(), path=paths.find_root())
            if len(repo.parents()) == 1:
                return
            if tool:
                if oldmergeenv:
                    os.environ['HGMERGE'] = oldmergeenv
                else:
                    del os.environ['HGMERGE']
            if self.notify_func:
                self.notify_func(self.notify_args)
            self.mergetool.set_sensitive(False)
            self.mergelabel.set_sensitive(False)
            self.mergebtn.set_sensitive(False)
            self.undobtn.set_sensitive(True)
            self.commitbtn.set_sensitive(True)
            self.commitbtn.grab_focus()
        self.switch_to(MODE_WORKING)
        self.cmd.execute(cmdline, cmd_done)

    def docommit(self):
        dlg = commit.run(ui.ui())
        dlg.set_transient_for(self)
        dlg.set_modal(True)
        dlg.set_notify_func(self.commit_notify, dlg)
        dlg.display()

    def commit_notify(self, dlg):
        # refresh the log tool
        if self.notify_func:
            self.notify_func(self.notify_args)
        # hide merge dialog
        self.hide()
        # hide commit tool
        dlg.ready = False  # disables refresh
        dlg.hide()
        gobject.timeout_add(50, self.destroy)

    def doundo(self):
        res = gdialog.Confirm(_('Confirm undo merge'), [], self,
                              _('Clean checkout of original revision?')).run()
        if res != gtk.RESPONSE_YES:
            return
        cmdline = ['hg', 'update', '--rev', self.localrev, '--clean']

        def cmd_done(returncode):
            self.switch_to(MODE_NORMAL, cmd=False)
            if self.notify_func:
                self.notify_func(self.notify_args)
            self.mergetool.set_sensitive(True)
            self.mergelabel.set_sensitive(True)
            self.mergebtn.set_sensitive(True)
            self.mergebtn.grab_focus()
            self.undobtn.set_sensitive(False)
            self.commitbtn.set_sensitive(False)
        self.switch_to(MODE_WORKING)
        self.cmd.execute(cmdline, cmd_done)

def run(ui, *pats, **opts):
    return MergeDialog(opts.get('rev'))
