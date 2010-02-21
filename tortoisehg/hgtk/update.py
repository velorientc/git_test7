# update.py - TortoiseHg's dialog for updating repo
#
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk

from mercurial import ui, error

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib

from tortoisehg.hgtk import csinfo, gtklib, gdialog

class UpdateDialog(gdialog.GDialog):
    """ Dialog to update Mercurial repo """
    def __init__(self, rev=None):
        gdialog.GDialog.__init__(self)
        self.rev = rev

    ### Start of Overriding Section ###

    def get_title(self, reponame):
        return _('Update - %s') % reponame

    def get_icon(self):
        return 'menucheckout.ico'

    def get_setting_name(self):
        return 'update'

    def get_body(self, vbox):
        # layout table
        table = gtklib.LayoutTable()
        vbox.pack_start(table, True, True, 2)
        self.table = table

        ## revision label & combobox
        self.revcombo = combo = gtk.combo_box_entry_new_text()
        entry = combo.child
        entry.set_width_chars(38)
        entry.connect('activate', lambda b: self.response(gtk.RESPONSE_OK))
        table.add_row(_('Update to:'), combo, padding=False)

        ## fill list of combo
        if self.rev != None:
            combo.append_text(str(self.rev))
        else:
            combo.append_text(self.repo.dirstate.branch())
        combo.set_active(0)
        for name in hglib.getlivebranch(self.repo):
            combo.append_text(name)

        tags = list(self.repo.tags())
        tags.sort()
        tags.reverse()
        for tag in tags:
            combo.append_text(hglib.toutf(tag))

        ## changeset summaries
        style = csinfo.labelstyle(contents=('%(rev)s', ' %(branch)s',
                       ' %(tags)s', '\n%(summary)s'), selectable=True, width=350)
        factory = csinfo.factory(self.repo, style=style)

        def add_with_pad(title, cslabel):
            label = gtk.Label(title)
            label.set_alignment(1, 0)
            headbox = gtk.VBox()
            headbox.pack_start(label, False, False, 2)
            headbox.pack_start(gtk.VBox())
            table.add_row(headbox, cslabel, yhopt=gtk.FILL|gtk.EXPAND)

        ## summary of target revision
        self.target_label = factory()
        add_with_pad(_('Target:'), self.target_label)

        ## summary of parent 1 revision
        self.parent1_label = factory()

        ## summary of parent 2 revision if needs
        self.ctxs = self.repo[None].parents()
        if len(self.ctxs) == 2:
            add_with_pad(_('Parent 1:'), self.parent1_label)
            self.parent2_label = factory()
            add_with_pad(_('Parent 2:'), self.parent2_label)
        else:
            add_with_pad(_('Parent:'), self.parent1_label)
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
        self.revcombo.connect('changed', lambda b: self.update_summaries())
        self.opt_clean.connect('toggled', lambda b: self.update_summaries())

        # prepare to show
        self.update_summaries()

    def get_extras(self, vbox):
        # append options
        self.opttable = gtklib.LayoutTable()
        vbox.pack_start(self.opttable, False, False)
        self.opttable.add_row(None, self.opt_merge, ypad=0)
        self.opttable.add_row(None, self.opt_showlog, ypad=0)

        # layout group
        layout = gtklib.LayoutGroup()
        layout.add(self.table, self.opttable, force=True)

    def get_buttons(self):
        return [('update', _('Update'), gtk.RESPONSE_OK),
                ('close', gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)]

    def get_default_button(self):
        return 'update'

    def get_action_map(self):
        return {gtk.RESPONSE_OK: self.update}

    def switch_to(self, normal, working, cmd):
        self.table.set_sensitive(normal)
        self.opttable.set_sensitive(normal)
        self.buttons['update'].set_property('visible', normal)
        self.buttons['close'].set_property('visible', normal)
        if normal:
            self.buttons['close'].grab_focus()
        if cmd and self.opt_showlog.get_active():
            self.cmd.show_log()

    def command_done(self, returncode, useraborted, *args):
        if returncode == 0:
            self.cmd.set_result(_('Updated successfully'), style='ok')
        elif useraborted:
            self.cmd.set_result(_('Canceled updating'), style='error')
        else:
            self.cmd.set_result(_('Failed to update'), style='error')

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

    ### End of Overriding Section ###

    def options_expanded(self, expander, *args):
        if expander.get_expanded():
            self.opttable.show_all()
        else:
            self.opttable.hide()

    def update_summaries(self):
        ctxs = self.ctxs
        self.parent1_label.update(ctxs[0])
        merge = len(ctxs) == 2
        if merge:
            self.parent2_label.update(ctxs[1])
        newrev = hglib.fromutf(self.revcombo.get_active_text())
        try:
            new_ctx = self.repo[newrev]
            if not merge and new_ctx.rev() == ctxs[0].rev():
                self.target_label.set_label(_('(same as parent)'))
                clean = self.opt_clean.get_active()
                self.buttons['update'].set_sensitive(clean)
            else:
                self.target_label.update(self.repo[newrev])
                self.buttons['update'].set_sensitive(True)
        except (error.LookupError, error.RepoLookupError, error.RepoError):
            self.target_label.set_label(_('unknown revision!'))
            self.buttons['update'].set_sensitive(False)

    def update(self):
        cmdline = ['hg', 'update', '--verbose']
        rev = hglib.fromutf(self.revcombo.get_active_text())
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
                return not clean and (p1 == pa or p2 == pa)
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
                    self.do_switch_to(gdialog.MODE_WORKING)
                    self.abort()
                    return
                else:
                    raise _('invalid dialog result: %s') % ret

        # start updating
        self.execute_command(cmdline)

def run(ui, *pats, **opts):
    return UpdateDialog(opts.get('rev'))
