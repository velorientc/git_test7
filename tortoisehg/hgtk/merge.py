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

from mercurial import ui, commands

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib

from tortoisehg.hgtk import csinfo, gtklib, gdialog

RESPONSE_MERGE =  1
RESPONSE_COMMIT = 2
RESPONSE_UNDO =   3

class MergeDialog(gdialog.GDialog):
    """ Dialog to merge revisions of a Mercurial repo """
    def __init__(self, rev0, rev1):
        gdialog.GDialog.__init__(self)

        self.revs = (rev0, rev1)
        self.set_notify_func(None)
        self.set_after_done(False)

    ### Start of Overriding Section ###

    def get_title(self, reponame):
        return _('Merging in %s') % reponame

    def get_icon(self):
        return 'menumerge.ico'

    def get_body(self, vbox):
        rev0, rev1 = self.revs
        prevs = [ctx.rev() for ctx in self.repo.parents()]
        if len(prevs) > 1:
            rev0, rev1 = prevs
        elif (not rev1 and rev1 != 0):
            gdialog.Prompt(_('Unable to merge'),
                           _('Must supply a target revision'), self).run()
            gtklib.idle_add_single_call(self.hide)
            return False
        elif (not rev0 and rev0 != 0):
            rev0 = prevs[0]
        elif rev1 == prevs[0]:
            # selected pair was backwards
            rev0, rev1 = rev1, rev0
        elif rev0 != prevs[0]:
            # working parent not in selected revision pair
            modified, added, removed, deleted = self.repo.status()[:4]
            if modified or added or removed or deleted:
                gdialog.Prompt(_('Unable to merge'),
                               _('Outstanding uncommitted changes'), self).run()
                gtklib.idle_add_single_call(self.hide)
                return False
            self.repo.ui.quiet = True
            commands.update(self.repo.ui, self.repo, rev=str(rev0), check=True)
            self.repo.ui.quiet = False

        # changeset info
        style = csinfo.panelstyle(contents=csinfo.PANEL_DEFAULT + ('ishead',),
                                  margin=5, padding=2)
        def markup_func(widget, item, value):
            if item == 'ishead' and value is False:
                text = _('Not a head revision!')
                return gtklib.markup(text, weight='bold')
            raise csinfo.UnknownItem(item)
        custom = csinfo.custom(markup=markup_func)
        factory = csinfo.factory(self.repo, custom, style, withupdate=True)

        info = factory(rev1, style={'label': _('Merge target (other)')})
        self.vbox.pack_start(info, False, False)
        self.otherframe = info
        self.otherrev = str(info.get_data('revnum'))

        info = factory(rev0, style={'label': _('Current revision (local)')})
        self.vbox.pack_start(info, False, False)
        self.localframe = info
        self.localrev = str(info.get_data('revnum'))

        # expander for advanced options
        expander = gtk.Expander(_('Advanced options'))
        self.vbox.pack_start(expander, False, False)

        # layout table for advanced options
        table = gtklib.LayoutTable()
        expander.add(table)
        
        vlist = gtk.ListStore(str,  # tool name
                              bool) # separator
        combo = gtk.ComboBoxEntry(vlist, 0)
        self.mergetool = combo
        combo.set_row_separator_func(lambda model, path: model[path][1])
        combo.child.set_width_chars(16)
        chtool = gtk.RadioButton(None, _('Use merge tool:'))
        self.mergelabel = chtool
        table.add_row(chtool, combo)
        prev = False
        for tool in hglib.mergetools(self.repo.ui):
            cur = tool.startswith('internal:')
            vlist.append((hglib.toutf(tool), prev != cur))
            prev = cur
        mtool = self.repo.ui.config('ui', 'merge', None)
        if mtool:
            combo.child.set_text(hglib.toutf(mtool))
        else:
            combo.child.set_text('')

        discard = gtk.RadioButton(chtool,
            _('Discard all changes from merge target (other) revision'))
        self.discard = discard
        table.add_row(discard)

        # prepare to show
        if len(self.repo.parents()) == 2:
            self.mergetool.set_sensitive(False)
            self.mergelabel.set_sensitive(False)
            self.discard.set_sensitive(False)
            self.buttons['merge'].set_sensitive(False)
            self.buttons['commit'].set_sensitive(True)
            self.buttons['undo'].set_sensitive(True)
        else:
            self.buttons['commit'].set_sensitive(False)
            self.buttons['undo'].set_sensitive(False)

    def get_buttons(self):
        return [('merge', _('Merge'), RESPONSE_MERGE),
                ('commit', _('Commit'), RESPONSE_COMMIT),
                ('undo', _('Undo'), RESPONSE_UNDO),
                ('close', gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)]

    def get_default_button(self):
        return 'merge'

    def get_action_map(self):
        return {RESPONSE_MERGE: self.domerge,
                RESPONSE_COMMIT: self.docommit,
                RESPONSE_UNDO: self.doundo}

    def switch_to(self, normal, working, cmd):
        self.otherframe.set_sensitive(normal)
        self.localframe.set_sensitive(normal)
        self.mergetool.set_property('visible', normal)
        self.discard.set_property('visible', normal)
        self.mergelabel.set_property('visible', normal)

        self.buttons['merge'].set_property('visible', normal)
        self.buttons['commit'].set_property('visible', normal)
        self.buttons['undo'].set_property('visible', normal)
        self.buttons['close'].set_property('visible', normal)

    def command_done(self, returncode, useraborted, type):
        hglib.invalidaterepo(self.repo)
        merged = undo = True
        if type == 'merge':
            if returncode == 0:
                self.cmd.set_result(_('Merged successfully'), style='ok')
            elif useraborted:
                self.cmd.set_result(_('Canceled merging'), style='error')
            else:
                self.cmd.set_result(_('Failed to merge'), style='error')
            if len(self.repo.parents()) == 1:
                return
            merged = False
            focus = 'commit'
        elif type == 'undo':
            if returncode == 0:
                self.cmd.set_result(_('Undo successfully'), style='ok')
            elif useraborted:
                self.cmd.set_result(_('Canceled undo'), style='error')
            else:
                self.cmd.set_result(_('Failed to undo'), style='error')
            undo = False
            focus = 'merge'
        else:
            raise _('unexpected type: %s') % type

        self.discard.set_sensitive(merged)
        self.mergetool.set_sensitive(merged)
        self.mergelabel.set_sensitive(merged)
        self.buttons['merge'].set_sensitive(merged)
        self.buttons['undo'].set_sensitive(undo)
        self.buttons['commit'].set_sensitive(undo)
        self.buttons[focus].grab_focus()

    def before_close(self):
        if len(self.repo.parents()) == 2:
            ret = gdialog.Confirm(_('Confirm Exit'), [], self,
                    _('To complete merging, you need to commit'
                      ' merged files in working directory.\n\n'
                      'Do you want to exit?')).run()
            if ret != gtk.RESPONSE_YES:
                return False
        return True

    ### End of Overriding Section ###

    def domerge(self):
        if self.discard.get_active():
            c = self.repo[None]
            if c.modified() or c.added() or c.removed():
                gdialog.Prompt(_('Cannot merge'),
                               _('Uncommitted local changes'), self).run()
                return
            # '.' is safer than self.localrev, in case the user has
            # pulled a fast one on us and updated from the CLI
            ret = gdialog.Confirm(_('Confirm Discard Changes'), [], self,
                _('The changes from revision %s and all unmerged parents'
                  ' will be discarded.\n\n'
                  'Are you sure this is what you want to do?')
                      % (self.otherframe.get_data('revid'))).run()
            if ret != gtk.RESPONSE_YES:
                return
            cmdline = ['hg', 'debugsetparents', '.', self.otherrev]
        else:
            tool = hglib.fromutf(self.mergetool.child.get_text())
            if tool:
                cmdline = ['hg', '--config', 'ui.merge=%s' % tool]
            else:
                cmdline = ['hg']
            cmdline.extend(['merge', '--rev', self.otherrev])
        self.execute_command(cmdline, 'merge')

    def docommit(self):
        def commit_notify():
            # refresh changelog
            if hasattr(self, 'notify_func') and self.notify_func:
                self.notify_func(*self.notify_args)
            # hide merge dialog
            self.hide()
            # hide commit tool
            dlg.ready = False  # disables refresh
            dlg.hide()
            # close self
            self.response(gdialog.RESPONSE_FORCE_CLOSE)

        from tortoisehg.hgtk import commit
        dlg = commit.run(ui.ui())
        dlg.set_transient_for(self)
        dlg.set_modal(True)
        dlg.set_notify_func(commit_notify)
        dlg.display()

    def doundo(self):
        res = gdialog.Confirm(_('Confirm undo merge'), [], self,
                              _('Clean checkout of original revision?')).run()
        if res != gtk.RESPONSE_YES:
            return
        cmdline = ['hg', 'update', '--rev', self.localrev, '--clean']
        self.execute_command(cmdline, 'undo')

def run(ui, *pats, **opts):
    return MergeDialog(None, opts.get('rev'))
