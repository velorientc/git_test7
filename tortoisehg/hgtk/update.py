# update.py - TortoiseHg's dialog for updating repo
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import gobject

from mercurial import hg, ui, error

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths, settings

from tortoisehg.hgtk import csinfo, gtklib, gdialog, hgcmd

MODE_NORMAL  = 'normal'
MODE_WORKING = 'working'

class UpdateDialog(gtk.Dialog):
    """ Dialog to update Mercurial repo """
    def __init__(self, rev=None):
        """ Initialize the Dialog """
        gtk.Dialog.__init__(self)
        gtklib.set_tortoise_icon(self, 'menucheckout.ico')
        gtklib.set_tortoise_keys(self)
        self.set_resizable(False)
        self.set_has_separator(False)

        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
        except error.RepoError:
            gtklib.idle_add_single_call(self.destroy)
            return
        self.repo = repo
        self.set_title(_('Update - %s') % hglib.get_reponame(repo))

        # add dialog buttons
        self.updatebtn = self.add_button(_('Update'), gtk.RESPONSE_OK)
        self.closebtn = self.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CLOSE)

        # persistent settings
        self.settings = settings.Settings('update')
        
        # layout table
        table = gtklib.LayoutTable()
        self.vbox.pack_start(table, True, True, 2)
        self.table = table

        ## revision label & combobox
        self.revcombo = combo = gtk.combo_box_entry_new_text()
        entry = combo.child
        entry.set_width_chars(38)
        entry.connect('activate', lambda b: self.response(gtk.RESPONSE_OK))
        table.add_row(_('Update to:'), combo, padding=False)

        ## fill list of combo
        if rev != None:
            combo.append_text(str(rev))
        else:
            combo.append_text(repo.dirstate.branch())
        combo.set_active(0)

        dblist = hglib.getdeadbranch(repo.ui)
        for name in repo.branchtags().keys():
            if name not in dblist:
                combo.append_text(name)

        tags = list(repo.tags())
        tags.sort()
        tags.reverse()
        for t in tags:
            combo.append_text(t)

        ## changeset summaries
        style = csinfo.labelstyle(contents=('%(rev)s', ' %(branch)s',
                       ' %(tags)s', '\n%(summary)s'), selectable=True, width=350)
        factory = csinfo.factory(repo, style=style)

        ## summary of target revision
        self.target_label = factory()
        table.add_row(_('Target:'), self.target_label)

        ## summary of parent 1 revision
        self.parent1_label = factory()

        ## summary of parent 2 revision if needs
        self.ctxs = repo[None].parents()
        if len(self.ctxs) == 2:
            table.add_row(_('Parent 1:'), self.parent1_label)
            self.parent2_label = factory()
            table.add_row(_('Parent 2:'), self.parent2_label)
        else:
            table.add_row(_('Parent:'), self.parent1_label)
            self.parent2_label = None

        ## option expander
        self.expander = gtk.Expander(_('Options:'))
        self.expander.connect('notify::expanded', self.options_expanded)

        ### update method (fixed)
        self.opt_clean = gtk.CheckButton(_('Discard local changes, '
                                           'no backup (-C/--clean)'))
        table.add_row(self.expander, self.opt_clean)

        ### other options (foldable), put later
        ### automatically merge, if possible (similar to command-line behavior)
        self.opt_merge = gtk.CheckButton(_('Always merge (when possible)'))

        ### always show command log widget
        self.opt_showlog = gtk.CheckButton(_('Always show log'))

        # signal handlers
        self.connect('response', self.dialog_response)
        self.revcombo.connect('changed', lambda b: self.update_summaries())
        self.opt_clean.connect('toggled', lambda b: self.update_summaries())

        # prepare to show
        self.load_settings()
        self.update_summaries()
        self.updatebtn.grab_focus()
        gtklib.idle_add_single_call(self.after_init)

    def load_settings(self):
        merge = self.settings.get_value('mergedefault', False)
        showlog = self.settings.get_value('showlog', False)
        self.opt_merge.set_active(merge)
        self.opt_showlog.set_active(showlog)

    def store_settings(self):
        checked = self.opt_merge.get_active()
        showlog = self.opt_showlog.get_active()
        self.settings.set_value('mergedefault', checked)
        self.settings.set_value('showlog', showlog)

        self.settings.write()

    def after_init(self):
        # append options
        self.opttable = gtklib.LayoutTable()
        self.vbox.pack_start(self.opttable, False, False)
        self.opttable.add_row(None, self.opt_merge, ypad=0)
        self.opttable.add_row(None, self.opt_showlog, ypad=0)

        # layout group
        layout = gtklib.LayoutGroup()
        layout.add(self.table, self.opttable, force=True)

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
        # Update button
        if response_id == gtk.RESPONSE_OK:
            self.update()
        # Close button or dialog closing by the user
        elif response_id in (gtk.RESPONSE_CLOSE, gtk.RESPONSE_DELETE_EVENT):
            if self.cmd.is_alive():
                ret = gdialog.Confirm(_('Confirm Abort'), [], self,
                                      _('Do you want to abort?')).run()
                if ret == gtk.RESPONSE_YES:
                    self.abort()
            else:
                self.store_settings()                
                self.destroy()
                return # close dialog
        # Abort button
        elif response_id == gtk.RESPONSE_CANCEL:
            self.abort()
        else:
            raise _('unexpected response id: %s') % response_id

        self.run() # don't close dialog

    def options_expanded(self, expander, *args):
        if expander.get_expanded():
            self.opttable.show_all()
        else:
            self.opttable.hide()

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

        self.table.set_sensitive(normal)
        self.opttable.set_sensitive(normal)
        self.updatebtn.set_property('visible', normal)
        self.closebtn.set_property('visible', normal)
        if cmd:
            self.cmd.set_property('visible', working)
            if self.opt_showlog.get_active():
                self.cmd.show_log()
        self.abortbtn.set_property('visible', working)

    def update_summaries(self):
        ctxs = self.ctxs
        self.parent1_label.update(ctxs[0])
        merge = len(ctxs) == 2
        if merge:
            self.parent2_label.update(ctxs[1])
        newrev = self.revcombo.get_active_text()
        try:
            new_ctx = self.repo[newrev]
            if not merge and new_ctx.rev() == ctxs[0].rev():
                self.target_label.set_label(_('(same as parent)'))
                self.updatebtn.set_sensitive(self.opt_clean.get_active())
            else:
                self.target_label.update(self.repo[newrev])
                self.updatebtn.set_sensitive(True)
        except (error.LookupError, error.RepoLookupError, error.RepoError):
            self.target_label.set_label(_('unknown revision!'))
            self.updatebtn.set_sensitive(False)

    def update(self):
        cmdline = ['hg', 'update', '--verbose']
        rev = self.revcombo.get_active_text()
        cmdline.append('--rev')
        cmdline.append(rev)

        if self.opt_clean.get_active():
            cmdline.append('--clean')
        else:
            cur = self.repo['.']
            node = self.repo[rev]
            def isclean():
                '''whether WD is changed'''
                wc = self.repo[None]
                return not (wc.modified() or wc.added() or wc.removed())
            def ismergedchange():
                '''whether the local changes are merged (have 2 parents)'''
                wc = self.repo[None]
                return len(wc.parents()) == 2
            def iscrossbranch(p1, p2):
                '''whether p1 -> p2 crosses branch'''
                pa = p1.ancestor(p2)
                return p1.branch() != p2.branch() or (p1 != pa and p2 != pa)
            def islocalmerge(p1, p2, clean=None):
                if clean is None:
                    clean = isclean()
                pa = p1.ancestor(p2)
                return not clean and p1.branch() == p2.branch() and \
                       (p1 == pa or p2 == pa)
            def confirmupdate(clean=None):
                if clean is None:
                    clean = isclean()

                msg = _('Detected uncommitted local changes in working tree.\n'
                        'Please select to continue:\n\n')
                data = {'discard': (_('&Discard'),
                                    _('Discard - discard local changes, no backup')),
                        'shelve': (_('&Shelve'),
                                   _('Shelve - launch Shelve tool and continue')),
                        'merge': (_('&Merge'),
                                  _('Merge - allow to merge with local changes')),
                        'cancel': (_('&Cancel'), None)}

                opts = [data['discard']]
                if not ismergedchange():
                    opts.append(data['shelve'])
                if islocalmerge(cur, node, clean):
                    opts.append(data['merge'])
                opts.append(data['cancel'])

                msg += '\n'.join([ desc for label, desc in opts if desc ])
                buttons = [ label for label, desc in opts ]
                cancel = len(opts) - 1
                retcode = gdialog.CustomPrompt(_('Confirm Update'), msg, self,
                                    buttons, default=cancel, esc=cancel).run()
                retlabel = buttons[retcode]
                retid = [ id for id, (label, desc) in data.items() \
                             if label == retlabel ][0]
                return dict([(id, id == retid) for id in data.keys()])
            # If merge-by-default, we want to merge whenever possible,
            # without prompting user (similar to command-line behavior)
            defaultmerge = self.opt_merge.get_active()
            clean = isclean()
            if clean:
                cmdline.append('--check')
            elif not (defaultmerge and islocalmerge(cur, node, clean)):
                ret = confirmupdate(clean)
                if ret['discard']:
                    cmdline.append('--clean')
                elif ret['shelve']:
                    def launch_shelve():
                        from tortoisehg.hgtk import thgshelve
                        dlg = thgshelve.run(ui.ui())
                        dlg.set_transient_for(self)
                        dlg.set_modal(True)
                        dlg.display()
                        dlg.connect('destroy', lambda w: self.update())
                    gtklib.idle_add_single_call(launch_shelve)
                    return # retry later, no need to destroy
                elif ret['merge']:
                    pass # no args
                elif ret['cancel']:
                    self.cmd.log.append(_('[canceled by user]\n'), error=True)
                    self.switch_to(MODE_WORKING)
                    self.abort()
                    return
                else:
                    raise _('invalid dialog result: %s') % ret

        def cmd_done(returncode, useraborted):
            self.switch_to(MODE_NORMAL, cmd=False)
            if hasattr(self, 'notify_func'):
                self.notify_func(self.notify_args)
            if returncode == 0:
                if not self.cmd.is_show_log():
                    self.response(gtk.RESPONSE_CLOSE)
                self.cmd.set_result(_('Updated successfully'), style='ok')
            elif useraborted:
                self.cmd.set_result(_('Canceled updating'), style='error')
            else:
                self.cmd.set_result(_('Failed to update'), style='error')
        self.switch_to(MODE_WORKING)
        self.cmd.execute(cmdline, cmd_done)

    def set_notify_func(self, func, *args):
        self.notify_func = func
        self.notify_args = args

def run(ui, *pats, **opts):
    return UpdateDialog(opts.get('rev'))
