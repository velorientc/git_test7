#
# commit.py - commit dialog for TortoiseHg
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
# Copyright (C) 2009 Steve Borho <steve@borho.org>
#

import os
import errno
import gtk
import gobject
import pango
import tempfile
import cStringIO
import time

from mercurial import ui, hg, util, patch

from thgutil.i18n import _
from thgutil import shlib, hglib

from hggtk.status import GStatus, FM_STATUS, FM_CHECKED, FM_PATH_UTF8
from hggtk.status import DM_REJECTED, DM_CHUNK_ID
from hggtk import gtklib, thgconfig, gdialog, hgcmd

class BranchOperationDialog(gtk.Dialog):
    def __init__(self, branch, close):
        gtk.Dialog.__init__(self, parent=None, flags=gtk.DIALOG_MODAL,
                          buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))
        gtklib.set_tortoise_keys(self)
        self.connect('response', self.response)
        self.set_title(_('Branch Operations'))
        self.newbranch = None
        self.closebranch = False

        lbl = gtk.Label(_('Changes take effect on next commit'))
        nochanges = gtk.RadioButton(None, _('No branch changes'))
        self.newbranchradio = gtk.RadioButton(nochanges,
                _('Open a new named branch'))
        self.closebranchradio = gtk.RadioButton(nochanges,
                _('Close current named branch'))
        self.branchentry = gtk.Entry()

        hbox = gtk.HBox()
        hbox.pack_start(self.newbranchradio, False, False, 2)
        hbox.pack_start(self.branchentry, True, True, 2)
        self.vbox.pack_start(hbox, True, True, 2)
        hbox = gtk.HBox()
        hbox.pack_start(self.closebranchradio, True, True, 2)
        self.vbox.pack_start(hbox, True, True, 2)
        hbox = gtk.HBox()
        hbox.pack_start(nochanges, True, True, 2)
        self.vbox.pack_start(hbox, True, True, 2)
        self.vbox.pack_start(lbl, True, True, 10)
        self.newbranchradio.connect('toggled', self.nbtoggle)

        self.newbranchradio.set_active(True)
        if branch:
            self.branchentry.set_text(branch)
            self.newbranchradio.set_active(True)
        elif close:
            self.closebranchradio.set_active(True)
        else:
            nochanges.set_active(True)
        self.show_all()

    def nbtoggle(self, radio):
        self.branchentry.set_sensitive(radio.get_active())

    def response(self, widget, response_id):
        if response_id != gtk.RESPONSE_CLOSE:
            self.destroy()
            return
        if self.newbranchradio.get_active():
            self.newbranch = self.branchentry.get_text()
        elif self.closebranchradio.get_active():
            self.closebranch = True
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

    def set_notify_func(self, func, args):
        self.notify_func = func
        self.notify_args = args

    def parse_opts(self):
        GStatus.parse_opts(self)

        # Need an entry, because extdiff code expects it
        if not self.test_opt('rev'):
            self.opts['rev'] = ''

    def get_title(self):
        root = hglib.toutf(os.path.basename(self.repo.root))
        user = self.opts.get('user')
        if user: user = 'as ' + user
        date = self.opts.get('date')
        pats = ' '.join(self.pats)
        if self.qnew:
            return root + ' qnew'
        elif self.mqmode:
            patch = self.repo.mq.lookup('qtip')
            return root + ' qrefresh ' + patch
        return ' '.join([root, 'commit', pats or '', user or '', date or ''])

    def get_icon(self):
        return 'menucommit.ico'

    def auto_check(self):
        if self.test_opt('check'):
            for entry in self.filemodel:
                if entry[FM_STATUS] in 'MAR':
                    entry[FM_CHECKED] = True
            self.update_check_count()
        self.opts['check'] = False


    def save_settings(self):
        settings = GStatus.save_settings(self)
        settings['commit-vpane'] = self.vpaned.get_position()
        return settings


    def load_settings(self, settings):
        self.connect('delete-event', self.delete)
        GStatus.load_settings(self, settings)
        self._setting_vpos = -1
        try:
            self._setting_vpos = settings['commit-vpane']
        except KeyError:
            pass


    def get_tbbuttons(self):
        tbbuttons = GStatus.get_tbbuttons(self)
        tbbuttons.insert(2, gtk.SeparatorToolItem())
        self.undo_button = self.make_toolbutton(gtk.STOCK_UNDO, _('_Undo'),
            self.undo_clicked, tip=_('undo recent commit'))
        self.commit_button = self.make_toolbutton(gtk.STOCK_OK, _('_Commit'),
            self.commit_clicked, tip=_('commit'))
        tbbuttons.insert(2, self.undo_button)
        tbbuttons.insert(2, self.commit_button)
        return tbbuttons


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

    def first_msg_popdown(self, combo, shown):
        combo.disconnect(self.popupid)
        self.popupid = None
        self.update_recent_messages()

    def update_recent_messages(self, msg=None):
        if msg is not None:
            self._mru_messages.add(msg)
            self.settings.write()
            if self.popupid is not None: return
        liststore = self.msg_cbbox.get_model()
        liststore.clear()
        for msg in self._mru_messages:
            sumline = msg.split("\n")[0]
            liststore.append([sumline, msg])

    def branch_clicked(self, button):
        dialog = BranchOperationDialog(self.nextbranch, self.closebranch)
        dialog.run()
        self.nextbranch = None
        self.closebranch = False
        if dialog.newbranch:
            self.nextbranch = dialog.newbranch
        elif dialog.closebranch:
            self.closebranch = True
        self.refresh_branchop()

    def get_body(self):
        status_body = GStatus.get_body(self)

        vbox = gtk.VBox()
        mbox = gtk.HBox()

        self.connect('thg-accept', self.thgaccept)
        self.branchbutton = gtk.Button()
        self.branchbutton.connect('clicked', self.branch_clicked)
        mbox.pack_start(self.branchbutton, False, False, 2)

        if hasattr(self.repo, 'mq'):
            label = gtk.Label('QNew: ')
            mbox.pack_start(label, False, False, 2)
            self.qnew_name = gtk.Entry()
            self.qnew_name.set_width_chars(20)
            self.qnew_name.connect('changed', self.qnew_changed)
            mbox.pack_start(self.qnew_name, False, False, 2)
        else:
            self.qnew_name = None

        liststore = gtk.ListStore(str, str)
        self.msg_cbbox = gtk.ComboBox(liststore)
        cell = gtk.CellRendererText()
        self.msg_cbbox.pack_start(cell, True)
        self.msg_cbbox.add_attribute(cell, 'text', 0)
        liststore.append([_('Recent Commit Messages...'), ''])
        self.msg_cbbox.set_active(0)
        self.popupid = self.msg_cbbox.connect('notify::popup-shown',
                                              self.first_msg_popdown)
        self.msg_cbbox.connect('changed', self.changed_cb)
        mbox.pack_start(self.msg_cbbox)
        vbox.pack_start(mbox, False, False)
        self._mru_messages = self.settings.mrul('recent_messages')

        frame = gtk.Frame()
        frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        frame.add(scroller)
        vbox.pack_start(frame)

        self.text = gtk.TextView()
        self.text.connect('populate-popup', self.msg_add_to_popup)
        self.text.modify_font(pango.FontDescription(self.fontcomment))
        scroller.add(self.text)

        self.vpaned = gtk.VPaned()
        self.vpaned.add1(vbox)
        self.vpaned.add2(status_body)
        gobject.idle_add(self.realize_settings)
        return self.vpaned

    def realize_settings(self):
        self.vpaned.set_position(self._setting_vpos)

    def thgaccept(self, window):
        self.commit_clicked(None)

    def get_menu_info(self):
        """Returns menu info in this order: merge, addrem, unknown,
        clean, ignored, deleted
        """
        merge, addrem, unknown, clean, ignored, deleted, unresolved, resolved \
                = GStatus.get_menu_info(self)
        return (merge + ((_('_commit'), self.commit_file),),
                addrem + ((_('_commit'), self.commit_file),),
                unknown + ((_('_commit'), self.commit_file),),
                clean,
                ignored,
                deleted + ((_('_commit'), self.commit_file),),
                unresolved,
                resolved,
               )


    def delete(self, window, event):
        if not self.should_live():
            self.destroy()
        else:
            return True

    def should_live(self, widget=None, event=None):
        # If there are more than a few character typed into the commit
        # message, ask if the exit should continue.
        live = False
        buf = self.text.get_buffer()
        if buf.get_char_count() > 10 and buf.get_modified():
            dialog = gdialog.Confirm(_('Confirm Exit'), [], self,
                    _('Save commit message at exit?'))
            res = dialog.run()
            if res == gtk.RESPONSE_YES:
                begin, end = buf.get_bounds()
                self.update_recent_messages(buf.get_text(begin, end))
                buf.set_modified(False)
            elif res != gtk.RESPONSE_NO:
                live = True
        if not live:
            self._destroying(widget)
        return live


    def reload_status(self):
        if not self.ready: return False
        success = GStatus.reload_status(self)
        self.check_merge()
        self.check_patch_queue()
        self.check_undo()
        self.refresh_branchop()
        return success


    ### End of overridable methods ###

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
        self.undo_button.set_sensitive(can_undo)


    def check_merge(self):
        self.get_toolbutton(_('Re_vert')).set_sensitive(not self.merging)
        self.get_toolbutton(_('_Add')).set_sensitive(not self.merging)
        self.get_toolbutton(_('_Remove')).set_sensitive(not self.merging)
        self.get_toolbutton(_('Move')).set_sensitive(not self.merging)

        if self.merging:
            # select all changes if repo is merged
            for entry in self.filemodel:
                if entry[FM_STATUS] in 'MARD':
                    entry[FM_CHECKED] = True
            self.update_check_count()

            # pre-fill commit message
            buf = self.text.get_buffer()
            buf.set_text(_('merge'))
            buf.set_modified(False)


    def check_patch_queue(self):
        '''See if an MQ patch is applied, switch to qrefresh mode'''
        self.qheader = None
        if self.mqmode:
            self.qheader = self.repo['qtip'].description()
            buf = self.text.get_buffer()
            if buf.get_char_count() == 0 or not buf.get_modified():
                if self.qnew:
                    buf.set_text('')
                else:
                    buf.set_text(self.qheader)
                buf.set_modified(False)
            c_btn = self.get_toolbutton(_('_Commit'))
            if self.qnew:
                c_btn.set_label(_('QNew'))
                c_btn.set_tooltip(self.tooltips, _('QNew'))
                self._hg_call_wrapper('Status', self.do_reload_status)
            else:
                c_btn.set_label(_('QRefresh'))
                c_btn.set_tooltip(self.tooltips, _('QRefresh'))
        elif self.qnew:
            c_btn = self.get_toolbutton(_('_Commit'))
            c_btn.set_label(_('QNew'))
            c_btn.set_tooltip(self.tooltips, _('QNew'))
            buf = self.text.get_buffer()
            if not buf.get_modified():
                buf.set_text('')
                buf.set_modified(False)
        else:
            c_btn = self.get_toolbutton(_('_Commit'))
            c_btn.set_label(_('_Commit'))
            c_btn.set_tooltip(self.tooltips, _('commit'))
        self.branchbutton.set_sensitive(not (self.mqmode or self.qnew))

    def commit_clicked(self, toolbutton, data=None):
        if not self.ready_message():
            return

        commitable = 'MAR'
        if self.merging:
            commit_list = self.relevant_files(commitable)
            # merges must be committed without specifying file list.
            self.hg_commit([])
        else:
            addremove_list = self.relevant_files('?!')
            if len(addremove_list) and self.should_addremove(addremove_list):
                commitable += '?!'

            commit_list = self.relevant_files(commitable)
            if len(commit_list) > 0:
                self.commit_selected(commit_list)
            elif len(self.filemodel) == 0 and self.qnew:
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
                if cf not in self.modified: continue
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
                    if patch.patchfile.__bases__:
                        # Mercurial 1.3
                        patch.internalpatch(fp, ui, 1, repo.root, files=pfiles,
                                        eolmode=None)
                    else:
                        # Mercurial 1.2
                        patch.internalpatch(fp, ui, 1, repo.root, files=pfiles)
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


    def commit_file(self, stat, file):
        if self.ready_message():
            if stat not in '?!' or self.should_addremove([file]):
                self.hg_commit([file])
                self.reload_status()
                shlib.shell_notify([self.repo.wjoin(file)])
        return True


    def undo_clicked(self, toolbutton, data=None):
        response = gdialog.Confirm(_('Confirm Undo commit'),
                [], self, _('Undo last commit')).run()
        if response != gtk.RESPONSE_YES:
            return

        tip = self.get_tip_rev(True)
        if not tip == self.last_commit_id:
            gdialog.Prompt(_('Undo commit'),
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
            gdialog.Prompt(_('Undo commit'),
                    _('Errors during rollback!'), self).run()


    def should_addremove(self, files):
        if self.test_opt('addremove'):
            return True
        else:
            response = gdialog.Confirm(_('Confirm Add/Remove'),
                    files, self,_('Add/Remove the following files?')).run()
            if response == gtk.RESPONSE_YES:
                # This will stay set for further commits (meaning no
                # more prompts). Problem?
                self.opts['addremove'] = True
                return True
        return False


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
            return
        
        lines = buf.get_text(buf.get_start_iter(),
                             buf.get_end_iter()).splitlines()
        
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
        
        begin, end = buf.get_bounds()
        self.opts['message'] = buf.get_text(begin, end)
        return True


    def hg_commit(self, files):
        if not self.repo.ui.config('ui', 'username'):
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
            self.repo = hg.repository(ui.ui(), self.repo.root)
            self.ui = self.repo.ui
            return

        cmdline  = ['hg', 'commit', '--verbose', '--repository', self.repo.root]

        if self.nextbranch:
            newbranch = hglib.fromutf(self.nextbranch)
            if newbranch in self.repo.branchtags():
                if newbranch not in [p.branch() for p in self.repo.parents()]:
                    response = gdialog.Confirm(_('Confirm Override Branch'),
                            [], self, _('A branch named "%s" already exists,\n'
                        'override?') % newbranch).run()
                else:
                    response = gtk.RESPONSE_YES
            else:
                response = gdialog.Confirm(_('Confirm New Branch'), [], self,
                        _('Create new named branch "%s"?') % newbranch).run()
            if response == gtk.RESPONSE_YES:
                self.repo.dirstate.setbranch(newbranch)
            elif response != gtk.RESPONSE_NO:
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
        if self.opts['addremove']:
            cmdline += ['--addremove']
        if self.opts['user']:
            cmdline.extend(['--user', self.opts['user']])
        if self.opts['date']:
            cmdline.extend(['--date', self.opts['date']])
        cmdline += ['--message', hglib.fromutf(self.opts['message'])]
        if self.qnew:
            cmdline += [hglib.fromutf(self.get_qnew_name())]
        cmdline += [self.repo.wjoin(x) for x in files]
        dialog = hgcmd.CmdDialog(cmdline, True)
        dialog.set_transient_for(self)
        dialog.run()
        dialog.hide()

        # refresh overlay icons and commit dialog
        if dialog.return_code() == 0:
            self.closebranch = False
            self.nextbranch = None
            self.opts['check'] = True  # recheck MAR after commit
            self.filechunks = {}       # do not keep chunks
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
            self.qnew_name.grab_focus() # set focus back
            
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
            gdialog.Prompt(_('Info required'),
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
        self.repo = hg.repository(self.ui, self.repo.root)
        return


def run(_ui, *pats, **opts):
    cmdoptions = {
        'user':opts.get('user', ''), 'date':opts.get('date', ''),
        'logfile':'', 'message':'',
        'modified':True, 'added':True, 'removed':True, 'deleted':True,
        'unknown':True, 'ignored':False,
        'exclude':[], 'include':[],
        'check': True, 'git':False, 'addremove':False,
    }
    return GCommit(_ui, None, None, pats, cmdoptions)
