# commit.py - Commit dialog for TortoiseHg
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2007 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import errno
import gtk
import gobject
import pango
import tempfile
import cStringIO
import time

from mercurial import hg, util, patch, cmdutil

from tortoisehg.util.i18n import _
from tortoisehg.util import shlib, hglib

from tortoisehg.hgtk.status import GStatus, FM_STATUS, FM_CHECKED
from tortoisehg.hgtk.status import FM_PATH, FM_PATH_UTF8
from tortoisehg.hgtk import csinfo, gtklib, thgconfig, gdialog, hgcmd

class BranchOperationDialog(gtk.Dialog):
    def __init__(self, branch, close, mergebranches):
        gtk.Dialog.__init__(self, parent=None, flags=gtk.DIALOG_MODAL,
                            buttons=(gtk.STOCK_OK, gtk.RESPONSE_OK,
                                     gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL),
                            title=_('Branch Operations'))
        gtklib.set_tortoise_icon(self, 'branch.ico')
        gtklib.set_tortoise_keys(self)
        self.set_resizable(False)
        self.set_has_separator(False)

        self.newbranch = None
        self.closebranch = False

        if mergebranches:
            lbl = gtk.Label(_('Select branch of merge commit'))
            branchcombo = gtk.combo_box_new_text()
            for name in mergebranches:
                branchcombo.append_text(name)
            branchcombo.set_active(0)
            self.vbox.pack_start(lbl, True, True, 2)
            self.vbox.pack_start(branchcombo, True, True, 2)
            self.connect('response', self.merge_response, branchcombo)
            self.show_all()
            return

        # create widgets
        nochanges = gtk.RadioButton(None, _('No branch changes'))
        self.newbranchradio = gtk.RadioButton(nochanges,
                _('Open a new named branch'))
        self.newbranchradio.set_active(True)
        self.branchentry = gtk.Entry()
        self.closebranchradio = gtk.RadioButton(nochanges,
                _('Close current named branch'))

        # layout table
        table = gtklib.LayoutTable()
        self.vbox.pack_start(table, True, True, 2)

        lbl = gtk.Label()
        lbl.set_markup(gtklib.markup(_('Changes take effect on next commit'),
                                     weight='bold'))
        table.add_row(lbl, padding=False, ypad=6)
        table.add_row(self.newbranchradio, self.branchentry)
        table.add_row(self.closebranchradio)
        table.add_row(nochanges)

        # signal handlers
        self.connect('response', self.response)
        self.newbranchradio.connect('toggled', self.nbtoggle)
        self.branchentry.connect('activate', self.activated)

        # prepare to show
        if branch:
            self.newbranch = branch
            self.branchentry.set_text(branch)
            self.newbranchradio.set_active(True)
        elif close:
            self.closebranch = close
            self.closebranchradio.set_active(True)
        else:
            nochanges.set_active(True)

        self.show_all()

    def nbtoggle(self, radio):
        self.branchentry.set_sensitive(radio.get_active())
        if radio.get_active():
            self.branchentry.grab_focus()

    def activated(self, entry):
        self.response(self, response_id=gtk.RESPONSE_OK)

    def response(self, widget, response_id):
        if response_id == gtk.RESPONSE_OK:
            if self.newbranchradio.get_active():
                self.newbranch = self.branchentry.get_text()
            elif self.closebranchradio.get_active():
                self.closebranch = True
            else:
                self.newbranch = None
                self.closebranch = False
        self.destroy()

    def merge_response(self, widget, response_id, combo):
        self.closebranch = False
        if response_id == gtk.RESPONSE_OK:
            row = combo.get_active()
            if row == 1:
                self.newbranch = combo.get_model()[row][0]
        self.destroy()


class GCommit(GStatus):
    """GTK+ based dialog for displaying repository status and committing
    changes.  Also provides related operations like add, delete, remove,
    revert, refresh, ignore, diff, and edit.
    """

    ### Overrides of base class methods ###

    def init(self):
        GStatus.init(self)
        self.mode = 'commit'
        self.nextbranch = None
        self.closebranch = False
        self.last_commit_id = None
        self.qnew = False
        self.notify_func = None
        self.patch_text = None
        self.qheader = None

    def get_help_url(self):
        return 'commit.html'

    def set_notify_func(self, func, args):
        self.notify_func = func
        self.notify_args = args

    def parse_opts(self):
        GStatus.parse_opts(self)

    def get_title(self):
        root = self.get_reponame()
        if self.is_merge():
            root = _('merging ') + root
        user = self.opts.get('user') or ''
        if user: user = 'as ' + user
        date = self.opts.get('date') or ''
        pats = ' '.join(self.pats) or ''
        if self.qnew:
            return root + _(' - qnew')
        elif self.mqmode:
            patch = self.repo.mq.lookup('qtip')
            return root + _(' - qrefresh ') + patch
        return root + ' '.join([_(' - commit'), pats, user, date])

    def get_icon(self):
        return 'menucommit.ico'

    def get_default_setting(self):
        return 'ui.username'

    def auto_check(self):
        if not self.test_opt('check'):
            return
        for row in self.filemodel:
            if row[FM_STATUS] in 'MAR' and row[FM_PATH] not in self.excludes:
                row[FM_CHECKED] = True
        self.update_check_count()
        self.opts['check'] = False


    def get_menu_list(self):
        def refresh(menu):
            self.reload_status()
        def toggle(button, type):
            show = button.get_active()
            statename = 'show' + type
            if getattr(self, statename) != show:
                frame = getattr(self, type + '_frame')
                if show:
                    frame.show()
                else:
                    frame.hide()
                setattr(self, statename, show)
        return [(_('_View'),
           [dict(text=_('Advanced'), ascheck=True, func=toggle,
                args=['advanced'], check=self.showadvanced),
            dict(text=_('Parents'), ascheck=True, func=toggle,
                args=['parents'], check=self.showparents),
            dict(text='----'),
            dict(text=_('Refresh'), func=refresh, icon=gtk.STOCK_REFRESH)]),
           (_('_Operations'), [
            dict(text=_('_Commit'), func=self.commit_clicked,
                icon=gtk.STOCK_OK),
            dict(name='undo', text=_('_Undo'), func=self.undo_clicked,
                icon=gtk.STOCK_UNDO),
            dict(text='----'),
            dict(name='diff', text=_('_Diff'), func=self.diff_clicked,
                icon=gtk.STOCK_JUSTIFY_FILL),
            dict(name='revert', text=_('Re_vert'), func=self.revert_clicked,
                icon=gtk.STOCK_MEDIA_REWIND),
            dict(name='add', text=_('_Add'), func=self.add_clicked,
                icon=gtk.STOCK_ADD),
            dict(name='remove', text=_('_Remove'), func=self.remove_clicked,
                icon=gtk.STOCK_DELETE),
            dict(name='move', text=_('Move'), func=self.move_clicked,
                icon=gtk.STOCK_JUMP_TO),
            dict(name='forget', text=_('_Forget'), func=self.forget_clicked,
                icon=gtk.STOCK_CLEAR)]),
           ]

    def save_settings(self):
        settings = GStatus.save_settings(self)
        settings['commit-vpane'] = self.vpaned.get_position()
        settings['showparents'] = self.showparents
        settings['showadvanced'] = self.showadvanced
        return settings


    def load_settings(self, settings):
        GStatus.load_settings(self, settings)
        self.setting_vpos = -1
        self.showparents = True
        self.showadvanced = False
        try:
            self.setting_vpos = settings['commit-vpane']
            self.showparents = settings['showparents']
            self.showadvanced = settings['showadvanced']
        except KeyError:
            pass


    def get_tbbuttons(self):
        # insert to head of toolbar
        tbbuttons = GStatus.get_tbbuttons(self)
        tbbuttons.insert(0, gtk.SeparatorToolItem())
        undo_btn = self.make_toolbutton(gtk.STOCK_UNDO, _('_Undo'),
            self.undo_clicked, name='undo', tip=_('undo recent commit'))
        commit_btn = self.make_toolbutton(gtk.STOCK_OK, _('_Commit'),
            self.commit_clicked, name='commit', tip=_('commit'))
        tbbuttons.insert(0, undo_btn)
        tbbuttons.insert(0, commit_btn)
        return tbbuttons

    def should_live(self, widget=None, event=None):
        # If there are more than a few character typed into the commit
        # message, ask if the exit should continue.
        live = False
        buf = self.text.get_buffer()
        if buf.get_char_count() > 10 and buf.get_modified():
            # response: 0=Yes, 1=No, 2=Cancel
            response = gdialog.CustomPrompt(_('Confirm Exit'),
                _('Save commit message at exit?'), self,
                (_('&Yes'), _('&No'), _('&Cancel')), 2, 2).run()
            if response == 0:
                begin, end = buf.get_bounds()
                self.update_recent_messages(buf.get_text(begin, end))
                buf.set_modified(False)
            elif response == 2:
                live = True
        if not live:
            self._destroying(widget)
        return live


    def refresh_complete(self):
        self.check_merge()
        self.check_patch_queue()
        self.check_undo()
        self.refresh_branchop()
        self.update_parent_labels()
        self.update_commit_button()
        if not self.committer_cbbox.get_active_text():
            user = self.opts['user'] or os.environ.get('HGUSER') or \
                   self.repo.ui.config('ui', 'username')
            if user:
                self.update_recent_committers(hglib.toutf(user))
        if not self.autoinc_entry.get_text():
            autoinc = self.repo.ui.config('tortoisehg', 'autoinc', '')
            self.autoinc_entry.set_text(hglib.toutf(autoinc))
        if self.qnew_name:
            self.qnew_name.set_sensitive(not self.is_merge())
        if self.qnew:
            self.qnew_name.grab_focus() # set focus back
            self.qnew_name.set_position(-1)

    def get_body(self):
        self.connect('delete-event', self.delete)
        status_body = GStatus.get_body(self)

        vbox = gtk.VBox()

        # Advanced bar
        self.advanced_frame = gtk.VBox()
        adv_hbox = gtk.HBox()
        self.advanced_frame.pack_start(adv_hbox, False, False)
        adv_hbox.pack_start(gtk.Label(_('Committer:')), False, False, 2)

        liststore = gtk.ListStore(str)
        self.committer_cbbox = gtk.ComboBoxEntry(liststore)
        cell = gtk.CellRendererText()
        self.committer_cbbox.pack_start(cell, True)
        adv_hbox.pack_start(self.committer_cbbox, True, True, 2)
        self._mru_committers = self.settings.mrul('recent_committers')
        self.update_recent_committers()
        committer = os.environ.get('HGUSER') or self.repo.ui.config('ui', 'username')
        if committer:
            self.update_recent_committers(hglib.toutf(committer))
        self.committer_cbbox.set_active(0)

        adv_hbox.pack_start(gtk.Label(_('Auto-includes:')), False, False, 2)
        self.autoinc_entry = gtk.Entry()
        adv_hbox.pack_start(self.autoinc_entry, False, False, 2)
        self.autopush = gtk.CheckButton(_('Push after commit'))
        pushafterci = self.repo.ui.configbool('tortoisehg', 'pushafterci')
        self.autopush.set_active(pushafterci)
        adv_hbox.pack_start(self.autopush, False, False, 2)

        vbox.pack_start(self.advanced_frame, False, False, 2)

        mbox = gtk.HBox()
        self.connect('thg-accept', self.thgaccept)
        self.branchbutton = gtk.Button()
        self.branchbutton.connect('clicked', self.branch_clicked)
        mbox.pack_start(self.branchbutton, False, False, 2)
        if self.is_merge():
            branches = [p.branch() for p in self.repo.parents()]
            if branches[0] == branches[1]:
                self.branchbutton.set_sensitive(False)

        if hasattr(self.repo, 'mq'):
            label = gtk.Label('QNew: ')
            mbox.pack_start(label, False, False, 2)
            self.qnew_name = gtk.Entry()
            self.qnew_name.set_sensitive(not self.is_merge())
            self.qnew_name.set_width_chars(20)
            self.qnew_name.connect('changed', self.qnew_changed)
            mbox.pack_start(self.qnew_name, False, False, 2)
        else:
            self.qnew_name = None

        liststore = gtk.ListStore(str, # summary line (utf-8)
                                  str) # full commit message
        self.msg_cbbox = gtk.ComboBox(liststore)
        cell = gtk.CellRendererText()
        self.msg_cbbox.pack_start(cell, True)
        self.msg_cbbox.add_attribute(cell, 'text', 0)
        liststore.append([_('Recent commit messages...'), ''])
        self.msg_cbbox.set_active(0)
        self.popupid = self.msg_cbbox.connect('notify::popup-shown',
                                              self.first_msg_popdown)
        self.msg_cbbox.connect('changed', self.changed_cb)
        mbox.pack_start(self.msg_cbbox)
        vbox.pack_start(mbox, False, False)
        self._mru_messages = self.settings.mrul('recent_messages')

        # change message field
        frame = gtk.Frame()
        frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        frame.add(scroller)
        vbox.pack_start(frame)

        accelgroup = gtk.AccelGroup()
        self.add_accel_group(accelgroup)
        mod = gtklib.get_thg_modifier()
        key, modifier = gtk.accelerator_parse('<alt>q')
        self.add_accelerator('thg-reflow', accelgroup, key,
                        modifier, gtk.ACCEL_VISIBLE)

        self.text = gtk.TextView()
        self.text.connect('populate-popup', self.msg_add_to_popup)
        self.connect('thg-reflow', self.thgreflow, self.text)
        self.text.modify_font(pango.FontDescription(self.fontcomment))
        scroller.add(self.text)
        gtklib.addspellcheck(self.text, self.repo.ui)

        vbox2 = gtk.VBox()
        vbox2.pack_start(status_body)

        # parent changeset info
        parents_vbox = gtk.VBox(spacing=1)
        self.parents_frame = parents_vbox
        style = csinfo.labelstyle(contents=(_('Parent: %(rev)s'),
                       ' %(athead)s', ' %(branch)s', ' %(tags)s',
                       ' %(summary)s'), selectable=True)
        def data_func(widget, item, ctx):
            if item == 'athead':
                return widget.get_data('ishead') or self.mqmode
            raise csinfo.UnknownItem(item)
        def markup_func(widget, item, value):
            if item == 'athead' and value is False:
                text = '[%s]' % _('not at head revision')
                return gtklib.markup(text, weight='bold')
            raise csinfo.UnknownItem(item)
        custom = csinfo.custom(data=data_func, markup=markup_func)
        factory = csinfo.factory(self.repo, custom, style)
        def add_parent():
            label = factory()
            parents_vbox.pack_start(label, False, False)
            return label
        self.parent1_label = add_parent()
        self.parent2_label = add_parent()
        parents_hbox = gtk.HBox()
        parents_hbox.pack_start(parents_vbox, False, False, 5)
        vbox2.pack_start(parents_hbox, False, False, 2)
        vbox2.pack_start(gtk.HSeparator(), False, False)

        self.vpaned = gtk.VPaned()
        self.vpaned.pack1(vbox, shrink=False)
        self.vpaned.pack2(vbox2, shrink=False)
        gtklib.idle_add_single_call(self.realize_settings)
        return self.vpaned

    def get_preview_tab_name(self):
        if self.qnew or self.mqmode:
            res = _('Patch Preview')
        else:
            res = _('Commit Preview')
        return res

    ### End of overridable methods ###


    def update_recent_committers(self, name=None):
        """ 'name' argument must be in UTF-8. """
        if name is not None:
            self._mru_committers.add(name)
            self._mru_committers.compact()
            self.settings.write()
        liststore = self.committer_cbbox.get_model()
        liststore.clear()
        for name in self._mru_committers:
            liststore.append([name])

    def changed_cb(self, combobox):
        model = combobox.get_model()
        index = combobox.get_active()
        if index >= 0:
            buf = self.text.get_buffer()
            if buf.get_char_count() and buf.get_modified():
                response = gdialog.Confirm(_('Confirm Discard Message'),
                        [], self, _('Discard current commit message?')).run()
                if response != gtk.RESPONSE_YES:
                    combobox.set_active(-1)
                    return
            buf.set_text(model[index][1])
            buf.set_modified(False)
            combobox.set_active(-1)

    def first_msg_popdown(self, combo, shown):
        combo.disconnect(self.popupid)
        self.popupid = None
        self.update_recent_messages()

    def update_recent_messages(self, msg=None):
        if msg:
            self._mru_messages.add(msg)
            self.settings.write()
            if self.popupid is not None:
                return
        liststore = self.msg_cbbox.get_model()
        liststore.clear()
        for msg in self._mru_messages:
            if not msg:
                continue
            sumline = hglib.toutf(hglib.tounicode(msg).splitlines()[0])
            liststore.append([sumline, msg])

    def branch_clicked(self, button):
        if self.is_merge():
            mb = [p.branch() for p in self.repo.parents()]
        else:
            mb = None
        dialog = BranchOperationDialog(self.nextbranch, self.closebranch, mb)
        dialog.run()
        self.nextbranch = None
        self.closebranch = False
        if dialog.newbranch:
            self.nextbranch = dialog.newbranch
        elif dialog.closebranch:
            self.closebranch = True
        self.refresh_branchop()

    def update_commit_button(self):
        label = _('Commit')
        tooltip = _('commit')

        if self.qnew:
            label = _('QNew')
            tooltip = _('create new MQ patch')
        elif self.mqmode:
            label = _('QRefresh')
            tooltip = _('refresh top MQ patch')
        else:
            plus, minus = _('_Commit (+1 head)'), _('_Commit (-1 head)')
            ctxs, isheads, ismerge = self.get_head_info()
            if not ismerge:
                if not isheads[0]:
                    label = plus
                    tooltip = _('parent is not a head, '
                                'commit to add a new head')
            else:
                if isheads[0] and isheads[1]:
                    label = minus
                    tooltip = _('commit to merge one head')
                elif not isheads[0] and not isheads[1]:
                    label = plus
                    tooltip = _('no parent is a head, '
                                'commit to add a new head')

        btn = self.get_toolbutton('commit')
        btn.set_label(label)
        btn.set_tooltip(self.tooltips, tooltip)

    def get_head_info(self):
        def ishead(ctx):
            return len(ctx.children()) == 0
        if self.mqmode:
            ctxs = self.repo['.'].parents()
        else:
            ctxs = self.repo[None].parents()
        isheads = [ishead(ctx) for ctx in ctxs]
        return ctxs, isheads, len(ctxs) == 2

    def update_parent_labels(self):
        ctxs, isheads, ismerge = self.get_head_info()
        self.parent1_label.update(ctxs[0])
        if not ismerge:
            self.parent2_label.hide()
        else:
            self.parent2_label.update(ctxs[1])
            self.parent2_label.show()

    def thgreflow(self, window, textview):
        buffer = textview.get_buffer()
        pos = buffer.get_property('cursor-position')
        start = buffer.get_iter_at_offset(0)
        end = start.copy()
        end.forward_to_end()

        text = hglib.tounicode(buffer.get_text(start, end))
        if pos == len(text):
            pos -= 1

        sentence_begin = text.rfind('\n\n', 0, pos)
        while sentence_begin >= 0 and text.rfind('\n\n', 0, pos - 1) == sentence_begin - 1:
            sentence_begin -= 1
        if sentence_begin == -1:
            sentence_begin = 0
        while sentence_begin < len(text) and text[sentence_begin] == '\n':
            sentence_begin += 1

        sentence_end = text.find('\n\n', sentence_begin + 1)
        if sentence_end == -1:
            sentence_end = len(text)

        pre_sentence = text[:sentence_begin]
        post_sentence = text[sentence_end:]
        sentence = text[sentence_begin:sentence_end]

        parts = sentence.replace('\r', '').replace('\n', ' ').replace('\t', ' ').split(' ')
        line_width = int(self.repo.ui.config('tortoisehg', 'messagewrap', 80))
        new_sentence = ['']

        for part in parts:
            if len(new_sentence[-1]) + len(part) + 1 > line_width:
                new_sentence.append('')
                
            new_sentence[-1] += '%s ' % part

        sentence = u'\n'.join([x.strip() for x in new_sentence]).encode('utf-8')

        new_pos = len(pre_sentence + sentence)
        buffer.set_text(pre_sentence + sentence + post_sentence)

        new_pos_iter = buffer.get_iter_at_offset(new_pos)
        buffer.place_cursor(new_pos_iter)
        m = buffer.create_mark('newcurspos', new_pos_iter, False)
        self.text.scroll_mark_onscreen(m)
        buffer.delete_mark(m)

    def realize_settings(self):
        self.vpaned.set_position(self.setting_vpos)
        if not self.showparents:
            self.parents_frame.hide()
        if not self.showadvanced:
            self.advanced_frame.hide()

    def thgaccept(self, window):
        self.commit_clicked(None)

    def get_custom_menus(self):
        def commit(menuitem, files):
            if self.ready_message() and self.isuptodate():
                self.hg_commit(files)
                self.reload_status()
                abs = [self.repo.wjoin(file) for file in files]
                shlib.shell_notify(abs)
        if self.is_merge():
            return ()
        else:
            return [(_('_Commit'), commit, 'MAR'),]

    def delete(self, window, event):
        if not self.should_live():
            self.destroy()
        else:
            return True

    def refresh_branchop(self):
        if self.nextbranch:
            text = _('new branch: ') + self.nextbranch
        elif self.closebranch:
            text = _('close branch: ') + self.repo[None].branch()
        else:
            text = _('branch: ') + self.repo[None].branch()
        self.branchbutton.set_label(text)

    def check_undo(self):
        can_undo = os.path.exists(self.repo.sjoin("undo")) and \
                self.last_commit_id is not None
        self.cmd_set_sensitive('undo', can_undo)

    def check_merge(self):
        if self.is_merge():
            # select all changes if repo is merged
            for entry in self.filemodel:
                if entry[FM_STATUS] in 'MARD':
                    entry[FM_CHECKED] = True
            self.update_check_count()

            # pre-fill commit message, if not modified
            buf = self.text.get_buffer()
            if not buf.get_modified():
                buf.set_text(_('Merge '))
                buf.set_modified(False)


    def check_patch_queue(self):
        'See if an MQ patch is applied, switch to qrefresh mode'
        self.qheader = None
        if self.mqmode:
            qtipctx = self.repo['qtip']
            self.qheader = qtipctx.description()
            self.committer_cbbox.child.set_text(hglib.toutf(qtipctx.user()))
            buf = self.text.get_buffer()
            if buf.get_char_count() == 0 or not buf.get_modified():
                if self.qnew:
                    buf.set_text('')
                else:
                    buf.set_text(self.qheader)
                buf.set_modified(False)
            if self.qnew:
                self.reload_status()
                self.qnew_name.grab_focus()
                self.qnew_name.set_position(-1)
                if self.patch_text:
                    self.diff_notebook.remove_page(self.ppage)
                    self.patch_text = None
            else:
                if not self.patch_text:
                    self.patch_text = gtk.TextView()
                    self.patch_text.set_wrap_mode(gtk.WRAP_NONE)
                    self.patch_text.set_editable(False)
                    self.patch_text.modify_font(self.difffont)
                    scroller = gtk.ScrolledWindow()
                    scroller.set_policy(gtk.POLICY_AUTOMATIC,
                                        gtk.POLICY_AUTOMATIC)
                    scroller.add(self.patch_text)
                    self.ppage = self.diff_notebook.append_page(scroller,
                                       gtk.Label(_('Patch Contents')))
                    self.diff_notebook.show_all()
                revs = cmdutil.revrange(self.repo, ['tip'])
                fp = cStringIO.StringIO()
                opts = patch.diffopts(self.ui, self.opts)
                patch.export(self.repo, revs, fp=fp, opts=opts)
                text = fp.getvalue().splitlines(True)
                buf = self.diff_highlight_buffer(text)
                self.patch_text.set_buffer(buf)
        elif self.qnew:
            buf = self.text.get_buffer()
            if not buf.get_modified():
                buf.set_text('')
                buf.set_modified(False)
            if self.patch_text:
                self.diff_notebook.remove_page(self.ppage)
                self.patch_text = None
        elif self.patch_text:
            buf = self.text.get_buffer()
            if not buf.get_modified():
                buf.set_text('')
                buf.set_modified(False)
            self.diff_notebook.remove_page(self.ppage)
            self.patch_text = None
        self.branchbutton.set_sensitive(not (self.mqmode or self.qnew))

    def commit_clicked(self, toolbutton, data=None):
        if not self.isuptodate():
            return

        def get_list(addremove=True):
            commitable = 'MAR'
            if addremove:
                ar_list = self.relevant_checked_files('?!')
                if len(ar_list) > 0 and self.should_addremove(ar_list):
                    commitable += '?!'
            return self.relevant_checked_files(commitable)

        if self.qnew:
            commit_list = get_list()
            self.commit_selected(commit_list)
        else:
            if not self.ready_message():
                return

            if self.is_merge():
                commit_list = get_list(addremove=False)
                # merges must be committed without specifying file list.
                self.hg_commit([])
            else:
                commit_list = get_list()
                if len(commit_list) > 0:
                    self.commit_selected(commit_list)
                elif self.qheader is not None:
                    self.commit_selected([])
                elif self.closebranch:
                    self.commit_selected([])
                else:
                    gdialog.Prompt(_('Nothing Commited'),
                           _('No committable files selected'), self).run()
                    return
        self.reload_status()
        files = [self.repo.wjoin(x) for x in commit_list]
        shlib.shell_notify(files)

    def commit_selected(self, files):
        # 1a. get list of chunks not rejected
        repo, ui = self.repo, self.repo.ui

        # 2. backup changed files, so we can restore them in the end
        backups = {}
        backupdir = repo.join('record-backups')
        try:
            os.mkdir(backupdir)
        except OSError, err:
            if err.errno != errno.EEXIST:
                gdialog.Prompt(_('Commit'),
                        _('Unable to create ') + backupdir, self).run()
                return
        try:
            # backup continues
            allchunks = []
            for f in files:
                cf = util.pconvert(f)
                if cf not in self.status[0]: continue
                if f not in self.filechunks: continue
                chunks = self.filechunks[f]
                if len(chunks) < 2: continue

                # unfiltered files do not go through backup-revert-patch cycle
                rejected = [c for c in chunks[1:] if not c.active]
                if len(rejected) == 0: continue
                allchunks.extend(chunks)
                fd, tmpname = tempfile.mkstemp(prefix=cf.replace('/', '_')+'.',
                                               dir=backupdir)
                os.close(fd)
                util.copyfile(repo.wjoin(cf), tmpname)
                backups[cf] = tmpname

            fp = cStringIO.StringIO()
            for n, c in enumerate(allchunks):
                if c.filename() in backups and c.active:
                    c.write(fp)
            dopatch = fp.tell()
            fp.seek(0)

            if backups:
                if self.qheader is not None:
                    # 3a. apply filtered patch to top patch's parent
                    hg.revert(repo, self._node1, backups.has_key)
                else:
                    # 3a. apply filtered patch to clean repo  (clean)
                    hg.revert(repo, repo.dirstate.parents()[0], backups.has_key)

            # 3b. (apply)
            if dopatch:
                try:
                    pfiles = {}
                    patch.internalpatch(fp, ui, 1, repo.root, files=pfiles,
                                        eolmode=None)
                    patch.updatedir(ui, repo, pfiles)
                except patch.PatchError, err:
                    s = str(err)
                    if s:
                        raise util.Abort(s)
                    else:
                        gdialog.Prompt(_('Commit'),
                                _('Unable to apply patch'), self).run()
                        return
            del fp

            # 4. We prepared working directory according to filtered patch.
            #    Now is the time to delegate the job to commit/qrefresh
            #    or the like!
            # it is important to first chdir to repo root -- we'll call a
            # highlevel command with list of pathnames relative to repo root
            cwd = os.getcwd()
            os.chdir(repo.root)
            try:
                self.hg_commit(files)
            finally:
                os.chdir(cwd)

            return
        finally:
            # 5. finally restore backed-up files
            try:
                for realname, tmpname in backups.iteritems():
                    util.copyfile(tmpname, repo.wjoin(realname))
                    os.unlink(tmpname)
                os.rmdir(backupdir)
            except OSError:
                pass


    def undo_clicked(self, toolbutton, data=None):
        response = gdialog.Confirm(_('Confirm Undo Commit'),
                [], self, _('Undo last commit')).run()
        if response != gtk.RESPONSE_YES:
            return

        tip = self.get_tip_rev(True)
        if not tip == self.last_commit_id:
            gdialog.Prompt(_('Undo Commit'),
                    _('Unable to undo!\n\n'
                    'Tip revision differs from last commit.'),
                    self).run()
            return

        try:
            self.repo.ui.quiet = True
            self.repo.rollback()
            self.repo.ui.quiet = False
            self.last_commit_id = None
            self.reload_status()
            time.sleep(0.5)     # give fs some time to pick up changes
            shlib.shell_notify([os.getcwd()])
        except:
            gdialog.Prompt(_('Undo Commit'),
                    _('Errors during rollback!'), self).run()


    def changelog_clicked(self, toolbutton, data=None):
        from tortoisehg.hgtk import history
        dlg = history.run(self.ui)
        dlg.display()
        return True


    def should_addremove(self, files):
        if self.test_opt('addremove'):
            return True
        response = gdialog.Confirm(_('Confirm Add/Remove'),
                files, self,_('Add/Remove the following files?')).run()
        if response != gtk.RESPONSE_YES:
            return False
        # This will stay set for further commits (meaning no more
        # prompts). Problem?
        self.opts['addremove'] = True
        if self.qnew or self.qheader is not None:
            cmdline = ['hg', 'addremove', '--verbose']
            cmdline += [self.repo.wjoin(x) for x in files]
            dialog = hgcmd.CmdDialog(cmdline, True)
            dialog.set_transient_for(self)
            dialog.run()
            dialog.hide()
        return True

    def ready_message(self):
        buf = self.text.get_buffer()
        if buf.get_char_count() == 0:
            gdialog.Prompt(_('Nothing Commited'),
                   _('Please enter commit message'), self).run()
            self.text.grab_focus()
            return False

        try:
            sumlen = int(self.repo.ui.config('tortoisehg', 'summarylen', 0))
            maxlen = int(self.repo.ui.config('tortoisehg', 'messagewrap', 0))
        except (TypeError, ValueError):
            gdialog.Prompt(_('Error'),
                   _('Message format configuration error'),
                   self).run()
            self.msg_config(None)
            return False
        
        lines = hglib.tounicode(buf.get_text(buf.get_start_iter(),
                                             buf.get_end_iter())).splitlines()
        
        if sumlen and len(lines[0].rstrip()) > sumlen:
            resp = gdialog.Confirm(_('Confirm Commit'), [], self,
                           _('The summary line length of %i is greater than'
                             ' %i.\n\nIgnore format policy and continue'
                             ' commit?') %
                                (len(lines[0].rstrip()), sumlen)).run()
            if resp != gtk.RESPONSE_YES:
                return False
        if sumlen and len(lines) > 1 and len(lines[1].strip()):
            resp = gdialog.Confirm(_('Confirm Commit'), [], self,
                           _('The summary line is not followed by a blank'
                             ' line.\n\nIgnore format policy and continue'
                             ' commit?')).run()
            if resp != gtk.RESPONSE_YES:
                return False
        if maxlen:
            start = int(sumlen > 0)
            tmp = [len(x.rstrip()) > maxlen for x in lines[start:]]
            errs = [str(x[1]+start+1) for x in zip(tmp, range(len(tmp)))
                    if x[0]]
            if errs:
                resp = gdialog.Confirm(_('Confirm Commit'), [], self,
                               _('The following lines are over the %i-'
                                 'character limit: %s.\n\nIgnore format'
                                 ' policy and continue commit?') %
                                    (maxlen, ', '.join(errs))).run()
                if resp != gtk.RESPONSE_YES:
                    return False
        return True
        
    def hg_commit(self, files):
        # get advanced options
        user = hglib.fromutf(self.committer_cbbox.get_active_text())
        if not user:
            gdialog.Prompt(_('Commit: Invalid username'),
                   _('Your username has not been configured.\n\n'
                    'Please configure your username and try again'),
                    self).run()

            # bring up the config dialog for user to enter their username.
            # But since we can't be sure they will do it right, we will
            # have them to retry, to re-trigger the checking mechanism.
            dlg = thgconfig.ConfigDialog(False)
            dlg.show_all()
            dlg.focus_field('ui.username')
            dlg.run()
            dlg.hide()
            self.refreshui()
            self.refresh_complete()
            return

        self.update_recent_committers(hglib.toutf(user))
        incs = hglib.fromutf(self.autoinc_entry.get_text())
        self.opts['include'] = [i.strip() for i in incs.split(',') if i.strip()]
        autopush = self.autopush.get_active()

        buf = self.text.get_buffer()
        begin, end = buf.get_bounds()
        self.opts['message'] = buf.get_text(begin, end)

        cmdline  = ['hg', 'commit', '--verbose']

        if self.nextbranch:
            # response: 0=Yes, 1=No, 2=Cancel
            if self.nextbranch in self.repo.branchtags():
                if self.nextbranch in [p.branch() for p in self.repo.parents()]:
                    response = 0
                else:
                    response = gdialog.CustomPrompt(_('Confirm Override Branch'),
                        _('A branch named "%s" already exists,\n'
                        'override?') % self.nextbranch, self,
                        (_('&Yes'), _('&No'), _('&Cancel')), 2, 2).run()
            else:
                response = gdialog.CustomPrompt(_('Confirm New Branch'),
                    _('Create new named branch "%s"?') % self.nextbranch,
                    self, (_('&Yes'), _('&No'), _('&Cancel')), 2, 2).run()
            if response == 0:
                self.repo.dirstate.setbranch(self.nextbranch)
            elif response == 2:
                return
        elif self.closebranch:
            cmdline.append('--close-branch')

        # call the threaded CmdDialog to do the commit, so the the large commit
        # won't get locked up by potential large commit. CmdDialog will also
        # display the progress of the commit operation.
        if self.qnew:
            cmdline[1] = 'qnew'
            cmdline.append('--force')
        elif self.qheader is not None:
            cmdline[1] = 'qrefresh'
            if not files:
                cmdline += ['-X', self.repo.root]
        elif self.opts['addremove']:
            cmdline += ['--addremove']
        if self.opts['user'] or user:
            cmdline.extend(['--user', self.opts['user'] or user])
        if self.opts['date']:
            cmdline.extend(['--date', self.opts['date']])
        files += self.opts['include']
        cmdline += ['--message', hglib.fromutf(self.opts['message'])]
        if self.qnew:
            cmdline += [hglib.fromutf(self.get_qnew_name())]
        cmdline += files
        if autopush:
            cmdline = (cmdline, ['hg', 'push'])
        dialog = hgcmd.CmdDialog(cmdline, True)
        dialog.set_transient_for(self)
        dialog.run()
        dialog.hide()

        # refresh overlay icons and commit dialog
        if dialog.return_code() == 0:
            self.closebranch = False
            self.nextbranch = None
            self.filechunks = {}       # force re-read of chunks
            buf = self.text.get_buffer()
            if buf.get_modified():
                self.update_recent_messages(self.opts['message'])
                buf.set_modified(False)
            if self.qnew:
                self.qnew_name.set_text('')
                hglib.invalidaterepo(self.repo)
                self.mode = 'commit'
                self.qnew = False
            elif self.qheader is None:
                self.text.set_buffer(gtk.TextBuffer())
                self.msg_cbbox.set_active(-1)
                self.last_commit_id = self.get_tip_rev(True)
            if self.notify_func:
                self.notify_func(self.notify_args)

    def get_tip_rev(self, refresh=False):
        if refresh:
            self.repo.invalidate()
        return self.repo['tip'].node()

    def get_qnew_name(self):
        return self.qnew_name and self.qnew_name.get_text().strip() or ''

    def qnew_changed(self, element):
        qnew = bool(self.get_qnew_name())
        if self.qnew != qnew:
            self.qnew = qnew
            self.mode = qnew and 'status' or 'commit'
            self.reload_status()
            
    def msg_add_to_popup(self, textview, menu):
        menu_items = (('----', None),
                      (_('Paste _Filenames'), self.msg_paste_fnames),
                      (_('App_ly Format'), self.msg_word_wrap),
                      (_('C_onfigure Format'), self.msg_config))
        for label, handler in menu_items:
            if label == '----':
                menuitem = gtk.SeparatorMenuItem()
            else:
                menuitem = gtk.MenuItem(label)
            if handler:
                menuitem.connect('activate', handler)
            menu.append(menuitem)
        menu.show_all()
        
    def msg_paste_fnames(self, sender):
        buf = self.text.get_buffer()
        fnames = [ file[FM_PATH_UTF8] for file in self.filemodel
                   if file[FM_CHECKED] ]
        buf.delete_selection(True, True)
        buf.insert_at_cursor('\n'.join(fnames))    

    def msg_word_wrap(self, sender):
        try:
            sumlen = int(self.repo.ui.config('tortoisehg', 'summarylen', 0))
            maxlen = int(self.repo.ui.config('tortoisehg', 'messagewrap', 0))
        except (TypeError, ValueError):
            sumlen = 0
            maxlen = 0
        if not (sumlen or maxlen):
            gdialog.Prompt(_('Info Required'),
                   _('Message format needs to be configured'),
                   self).run()
            self.msg_config(None)
            return

        buf = self.text.get_buffer()
        lines = buf.get_text(buf.get_start_iter(),
                             buf.get_end_iter()).splitlines()
        if not lines:
            return
        
        if sumlen and len(lines[0].rstrip()) > sumlen:
            gdialog.Prompt(_('Warning'),
                   _('The summary line length of %i is greater than %i') %
                         (len(lines[0].rstrip()), sumlen),
                   self).run()
        if sumlen and len(lines) > 1 and len(lines[1].strip()):
            gdialog.Prompt(_('Warning'),
                   _('The summary line is not followed by a blank line'),
                   self).run()
        if not maxlen:
            return
        
        lnum = int(sumlen > 0)
        while lnum < len(lines):
            lines[lnum] = lines[lnum].rstrip() + ' '
            if lines[lnum].endswith('. '):
                lines[lnum] += ' '
            if len(lines[lnum].rstrip()) > maxlen:
                ind = lines[lnum].rfind(' ', 0, maxlen+1) + 1
                if ind > 0:
                    if lnum == len(lines)-1 or not lines[lnum+1].strip():
                        lines.insert(lnum+1, lines[lnum][ind:].lstrip())
                    else:
                        lines[lnum+1] = lines[lnum][ind:].lstrip() \
                                        + lines[lnum+1]
                    lines[lnum] = lines[lnum][0:ind].rstrip()
            lnum += 1
        buf.set_text('\n'.join(lines))                       

    def msg_config(self, sender):
        dlg = thgconfig.ConfigDialog(True)
        dlg.show_all()
        dlg.focus_field('tortoisehg.summarylen')
        dlg.run()
        dlg.hide()
        self.refreshui()
        return


def run(_ui, *pats, **opts):
    cmdoptions = {
        'user':opts.get('user', ''), 'date':opts.get('date', ''),
        'logfile':'', 'message':'',
        'modified':True, 'added':True, 'removed':True, 'deleted':True,
        'unknown':True, 'ignored':False,
        'exclude':[], 'include':[], 'rev':[],
        'check': True, 'git':False, 'addremove':False,
    }
    return GCommit(_ui, None, None, pats, cmdoptions)
