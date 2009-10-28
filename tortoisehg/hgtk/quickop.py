# quickop.py - TortoiseHg's dialog for quick dirstate operations
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import gobject
import pango

from mercurial import hg, ui, cmdutil

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths, shlib
from tortoisehg.util.hglib import RepoError

from tortoisehg.hgtk import hgcmd, gtklib, gdialog

MODE_NORMAL  = 'normal'
MODE_WORKING = 'working'

class QuickOpDialog(gtk.Dialog):
    'Dialog for performing quick dirstate operations'
    def __init__(self, command, pats):
        gtk.Dialog.__init__(self)
        gtklib.set_tortoise_icon(self, 'hg.ico')
        gtklib.set_tortoise_keys(self)
        self.set_resizable(False)
        self.set_size_request(450, 300)
        self.set_has_separator(False)
        self.connect('response', self.dialog_response)

        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
        except hglib.RepoError:
            gtklib.idle_add_single_call(self.destroy)
            return

        # Handle rm alias
        if command == 'rm':
            command = 'remove'

        os.chdir(repo.root)
        self.repo = repo
        self.set_title(hglib.get_reponame(repo) + ' - hg ' + command)
        self.command = command

        labels = { 'add': (_('Select files to add'), _('Add')),
                   'forget': (_('Select files to forget'), _('Forget')),
                   'revert': (_('Select files to revert'), _('Revert')),
                   'remove': (_('Select files to remove'), _('Remove')),
                }

        # add dialog buttons
        self.gobutton = self.add_button(labels[command][1], gtk.RESPONSE_OK)
        self.closebtn = self.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CLOSE)

        lbl = gtk.Label(labels[command][0])
        lbl.set_alignment(0, 0)
        self.vbox.pack_start(lbl, False, False, 8)

        def keypressed(tree, event):
            'Make spacebar toggle selected rows'
            if event.keyval != 32:
                return False
            def toggler(model, path, bufiter):
                model[path][0] = not model[path][0]
            selection = tree.get_selection()
            selection.selected_foreach(toggler)
            return True

        # add file list treeview
        fm = gtk.ListStore(bool, # Checked
                           str,  # Path
                           str,  # Path-UTF8
                           str)  # Status
        self.filetree = gtk.TreeView(fm)
        self.filetree.connect('key-press-event', keypressed)
        self.filetree.set_headers_clickable(True)
        self.filetree.set_reorderable(False)
        if hasattr(self.filetree, 'set_rubber_banding'):
            self.filetree.set_rubber_banding(True)
        fontlist = repo.ui.config('gtools', 'fontlist', 'MS UI Gothic 9')
        self.filetree.modify_font(pango.FontDescription(fontlist))

        def select_toggle(cell, path):
            fm[path][0] = not fm[path][0]

        # file selection checkboxes
        toggle_cell = gtk.CellRendererToggle()
        toggle_cell.connect('toggled', select_toggle)
        toggle_cell.set_property('activatable', True)

        col = gtk.TreeViewColumn('', toggle_cell, active=0)
        col.set_resizable(False)
        self.filetree.append_column(col)

        col = gtk.TreeViewColumn(_('status'), gtk.CellRendererText(), text=3)
        self.filetree.append_column(col)

        col = gtk.TreeViewColumn(_('path'), gtk.CellRendererText(), text=2)
        self.filetree.append_column(col)

        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(self.filetree)
        self.vbox.pack_start(scroller, True, True, 8)

        def toggleall(button):
            for row in self.filetree.get_model():
                row[0] = not row[0]

        hbox = gtk.HBox()
        tb = gtk.Button(_('Toggle all selections'))
        tb.connect('pressed', toggleall)
        self.toggleall = tb
        hbox.pack_start(tb, False, False, 0)
        self.vbox.pack_start(hbox, False, False, 2)

        types = { 'add' : 'I?',
                  'forget' : 'MAR!C',
                  'revert' : 'MAR!',
                  'remove' : 'MAR!CI?',
                }
        filetypes = types[command]

        try:
            matcher = cmdutil.match(repo, pats)
            status = repo.status(match=matcher,
                                 clean='C' in filetypes,
                                 ignored='I' in filetypes,
                                 unknown='?' in filetypes)
        except IOError:
            pass

        (modified, added, removed, deleted, unknown, ignored, clean) = status
        if 'M' in filetypes:
            for f in modified:
                fm.append([True, f, hglib.toutf(f), _('modified')])
        if 'A' in filetypes:
            for f in added:
                fm.append([True, f, hglib.toutf(f), _('added')])
        if 'R' in filetypes:
            for f in removed:
                fm.append([True, f, hglib.toutf(f), _('removed')])
        if '!' in filetypes:
            for f in deleted:
                fm.append([True, f, hglib.toutf(f), _('missing')])
        if '?' in filetypes:
            for f in unknown:
                fm.append([True, f, hglib.toutf(f), _('unknown')])
        if 'I' in filetypes:
            for f in ignored:
                if command == 'remove' or f in pats:
                    fm.append([True, f, hglib.toutf(f), _('ignored')])
        if 'C' in filetypes:
            for f in clean:
                if command == 'remove' or f in pats:
                    fm.append([True, f, hglib.toutf(f), _('clean')])

        if not len(fm):
            gdialog.Prompt(_('No appropriate files'),
                           _('No files found for this operation'), self).run()
            gtklib.idle_add_single_call(self.destroy)
            self.hide()
            return

        # prepare to show
        self.gobutton.grab_focus()
        gtklib.idle_add_single_call(self.after_init)

    def after_init(self):
        # CmdWidget
        self.cmd = hgcmd.CmdWidget()
        self.cmd.show_all()
        self.cmd.hide()
        self.vbox.pack_start(self.cmd, False, False, 6)

        # abort button
        self.abortbtn = self.add_button(_('Abort'), gtk.RESPONSE_CANCEL)
        self.abortbtn.hide()

    def abort(self):
        self.cmd.stop()
        self.cmd.show_log()
        self.switch_to(MODE_NORMAL, cmd=False)

    def dialog_response(self, dialog, response_id):
        # go button
        if response_id == gtk.RESPONSE_OK:
            self.operation(self.repo)
        # Close button or dialog closing by the user
        elif response_id in (gtk.RESPONSE_CLOSE, gtk.RESPONSE_DELETE_EVENT):
            if hasattr(self, 'cmd') and self.cmd.is_alive():
                ret = gdialog.Confirm(_('Confirm Abort'), [], self,
                                      _('Do you want to abort?')).run()
                if ret == gtk.RESPONSE_YES:
                    self.abort()
            else:
                return # close dialog
        # Abort button
        elif response_id == gtk.RESPONSE_CANCEL:
            self.abort()
        else:
            raise _('unexpected response id: %s') % response_id

        self.run() # don't close dialog

    def switch_to(self, mode, cmd=True):
        if mode == MODE_NORMAL:
            normal = True
            self.closebtn.grab_focus()
        elif mode == MODE_WORKING:
            normal = False
            self.abortbtn.grab_focus()
        else:
            raise _('unknown mode name: %s') % mode
        working = not normal

        self.filetree.set_sensitive(normal)
        self.toggleall.set_sensitive(normal)
        self.gobutton.set_property('visible', normal)
        self.closebtn.set_property('visible', normal)
        if cmd:
            self.cmd.set_property('visible', working)
        self.abortbtn.set_property('visible', working)

    def operation(self, repo):
        fm = self.filetree.get_model()
        deleting = self.command == 'remove'
        list, dellist = [], []
        for row in fm:
            if not row[0]: continue
            if deleting and row[3] in (_('unknown'), _('ignored')):
                dellist.append(row[1])
            else:
                list.append(row[1])

        if not (list or dellist):
            gdialog.Prompt(_('No files selected'),
                           _('No operation to perform'), self).run()
            return

        for file in dellist:
            try:
                os.unlink(file)
            except IOError:
                pass

        if not list:
            gtklib.idle_add_single_call(self.response, gtk.RESPONSE_CLOSE)
            return

        cmdline = ['hg', self.command, '--verbose'] + list

        def cmd_done(returncode, useraborted):
            self.switch_to(MODE_NORMAL, cmd=False)
            if returncode == 0:
                shlib.shell_notify(list)
                if not self.cmd.is_show_log():
                    self.response(gtk.RESPONSE_CLOSE)
                self.cmd.set_result(_('Successfully'), style='ok')
            elif useraborted:
                self.cmd.set_result(_('Canceled'), style='error')
            else:
                self.cmd.set_result(_('Failed'), style='error')
        self.switch_to(MODE_WORKING)
        self.cmd.execute(cmdline, cmd_done)

def run(ui, *pats, **opts):
    pats = hglib.canonpaths(pats)
    if opts.get('canonpats'):
        pats = list(pats) + opts['canonpats']
    return QuickOpDialog(opts.get('alias'), pats)
