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

from mercurial import hg, ui

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths
from tortoisehg.util.hglib import LookupError, RepoLookupError, RepoError

from tortoisehg.hgtk import hgcmd, gtklib, gdialog

MODE_NORMAL   = 'normal'
MODE_UPDATING = 'updating'

class UpdateDialog(gtk.Dialog):
    """ Dialog to update Mercurial repo """
    def __init__(self, rev=None):
        """ Initialize the Dialog """
        gtk.Dialog.__init__(self)
        gtklib.set_tortoise_icon(self, 'menucheckout.ico')
        gtklib.set_tortoise_keys(self)
        self.set_resizable(False)
        self.set_size_request(450, -1)
        self.set_has_separator(False)
        self.connect('response', self.dialog_response)
        self.connect('delete-event', self.delete_event)

        try:
            repo = hg.repository(ui.ui(), path=paths.find_root())
            self.repo = repo
        except hglib.RepoError:
            gobject.idle_add(self.destroy)
            return

        reponame = hglib.toutf(os.path.basename(repo.root))
        self.set_title(_('Update - %s') % reponame)

        # add dialog buttons
        self.updatebtn = self.add_button(_('Update'), gtk.RESPONSE_OK)
        self.closebtn = self.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CLOSE)

        # layout table for fixed items
        table = gtklib.LayoutTable(width=9)
        self.tables = dict(fixed=table)
        self.vbox.pack_start(table, True, True, 2)

        ## revision label & combobox
        self.revcombo = combo = gtk.combo_box_entry_new_text()
        entry = combo.child
        entry.connect('activate', lambda b: self.update(repo))
        entry.set_width_chars(38)
        table.add_row(_('Update to:'), combo, expand=True)

        ## update method
        btn = gtk.CheckButton(_('Discard local changes, no backup (-C/--clean)'))
        self.opt_clean = btn
        table.add_row('', btn)

        ## fill list of combo
        if rev != None:
            combo.append_text(str(rev))
        else:
            combo.append_text(repo.dirstate.branch())
        combo.set_active(0)

        dblist = self.repo.ui.config('tortoisehg', 'deadbranch', '')
        deadbranches = [ x.strip() for x in dblist.split(',') ]
        for name in self.repo.branchtags().keys():
            if name not in deadbranches:
                combo.append_text(name)

        tags = list(repo.tags())
        tags.sort()
        tags.reverse()
        for t in tags:
            combo.append_text(t)

        # layout table for summaries
        table = gtklib.LayoutTable(width=9)
        self.tables['summary'] = table
        self.vbox.pack_start(table)

        self.show_summaries(True)

        self.opt_clean.connect('toggled', lambda b: self.update_summaries())

        # prepare to show
        self.updatebtn.grab_focus()
        gobject.idle_add(self.after_init)

    def after_init(self):
        # CmdWidget
        self.cmd = hgcmd.CmdWidget()
        self.cmd.show_all()
        self.cmd.hide()
        self.vbox.pack_start(self.cmd, True, True, 6)

        # cancel button
        self.cancelbtn = gtk.Button(_('Cancel'))
        self.cancelbtn.connect('clicked', self.cancel_clicked)
        self.action_area.pack_end(self.cancelbtn)

    def build_summaries(self):
        table = self.tables['summary']
        
        def new_label():
            label = gtk.Label('-')
            label.set_selectable(True)
            label.set_line_wrap(True)
            label.set_size_request(350, -1)
            hb = gtk.HBox()
            hb.pack_start(label, False, False)
            return hb, label

        # summary of new revision
        hb, label = new_label()
        table.add_row('Target:', hb, expand=True)
        self.new_rev_label = label

        # summary of current revision(s)
        hb, label = new_label()
        self.current_rev_label1 = label

        self.ctxs = self.repo[None].parents()
        if len(self.ctxs) == 2:
            table.add_row(_('Parent 1:'), hb)
            hb, label = new_label()
            table.add_row('Parent 2:', hb, expand=True)
            self.current_rev_label2 = label
        else:
            table.add_row(_('Parent:'), hb, expand=True)
            self.current_rev_label2 = None
        table.show_all()
        self.revcombo.connect('changed', lambda b: self.update_summaries())

    def dialog_response(self, dialog, response_id):
        if response_id == gtk.RESPONSE_OK:
            self.update(self.repo)
        elif not self.cmd.is_alive():
            self.destroy()

    def delete_event(self, dialog, event):
        if self.cmd.is_alive():
            ret = gdialog.Confirm(_('Confirm Cancel'), [], self,
                                  _('Do you want to cancel updating?')).run()
            if ret == gtk.RESPONSE_YES:
                self.cancel_clicked(self.cancelbtn)
            return True
        self.destroy()

    def cancel_clicked(self, button):
        self.cmd.stop()
        self.cmd.show_log()
        self.switch_to(MODE_NORMAL, cmd=False)

    def switch_to(self, mode, cmd=True):
        if mode == MODE_NORMAL:
            normal = True
            self.closebtn.grab_focus()
        elif mode == MODE_UPDATING:
            normal = False
            self.cancelbtn.grab_focus()
        else:
            raise _('unknown mode name: %s') % mode
        updating = not normal

        for table in self.tables.values():
            table.set_sensitive(normal)
        self.updatebtn.set_property('visible', normal)
        self.closebtn.set_property('visible', normal)
        if cmd:
            self.cmd.set_property('visible', updating)
        self.cancelbtn.set_property('visible', updating)

    def show_summaries(self, visible=True):
        if visible and not hasattr(self, 'ctxs'):
            self.build_summaries()
        if hasattr(self, 'ctxs'):
            self.update_summaries()
        table = self.tables['summary']
        table.set_property('visible', visible)

    def update_summaries(self):
        def setlabel(label, ctx):
            revision = str(ctx.rev())
            hash = str(ctx)
            summary = gtklib.markup_escape_text(hglib.toutf(
                                ctx.description().split('\n')[0]))
            face = 'monospace'
            size = '9000'

            format = '<span face="%s" size="%s">%s (%s)\n</span>'
            t = format % (face, size, revision, hash)

            branch = ctx.branch()
            if branch != 'default':
                format = '<span color="%s" background="%s"> %s </span> '
                t += format % ('black', '#aaffaa', branch)

            tags = self.repo.nodetags(ctx.node())
            format = '<span color="%s" background="%s"> %s </span> '
            for tag in tags:
                t += format % ('black', '#ffffaa', tag)

            t += summary
            label.set_markup(t)

        ctxs = self.ctxs
        setlabel(self.current_rev_label1, ctxs[0])
        merge = len(ctxs) == 2
        if merge:
            setlabel(self.current_rev_label2, ctxs[1])
        newrev = self.revcombo.get_active_text()
        try:
            new_ctx = self.repo[newrev]
            if not merge and new_ctx.rev() == ctxs[0].rev():
                self.new_rev_label.set_label(_('(same as parent)'))
                self.updatebtn.set_sensitive(self.opt_clean.get_active())
            else:
                setlabel(self.new_rev_label, self.repo[newrev])
                self.updatebtn.set_sensitive(True)
        except (LookupError, RepoLookupError, RepoError):
            self.new_rev_label.set_label(_('unknown revision!'))
            self.updatebtn.set_sensitive(False)

    def update(self, repo):
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
            clean = isclean()
            if clean:
                cmdline.append('--check')
            else:
                ret = confirmupdate(clean)
                if ret['discard']:
                    cmdline.append('--clean')
                elif ret['shelve']:
                    from tortoisehg.hgtk import thgshelve
                    dlg = thgshelve.run(ui.ui())
                    dlg.set_transient_for(self)
                    dlg.set_modal(True)
                    dlg.display()
                    dlg.connect('destroy', lambda w: self.update(repo))
                    return # retry later, no need to destroy
                elif ret['merge']:
                    pass # no args
                elif ret['cancel']:
                    self.destroy()
                    return
                else:
                    raise _('invalid dialog result: %s') % ret

        def cmd_done(returncode):
            self.switch_to(MODE_NORMAL, cmd=False)
            if hasattr(self, 'notify_func'):
                self.notify_func(self.notify_args)
            if returncode == 0 and not self.cmd.is_show_log():
                self.destroy()
        self.switch_to(MODE_UPDATING)
        self.cmd.execute(cmdline, cmd_done)

    def set_notify_func(self, func, *args):
        self.notify_func = func
        self.notify_args = args

def run(ui, *pats, **opts):
    return UpdateDialog(opts.get('rev'))
