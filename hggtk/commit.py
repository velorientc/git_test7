#
# commit.py - commit dialog for TortoiseHg
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
# Copyright (C) 2009 Steve Borho <steve@borho.org>
#

import os
import pygtk
pygtk.require('2.0')
import errno
import gtk
import pango
import tempfile
import cStringIO

from mercurial.i18n import _
from mercurial.node import *
from mercurial import ui, hg
from shlib import shell_notify
from gdialog import *
from status import *
from hgcmd import CmdDialog
from hglib import fromutf

class GCommit(GStatus):
    """GTK+ based dialog for displaying repository status and committing
    changes.  Also provides related operations like add, delete, remove,
    revert, refresh, ignore, diff, and edit.
    """

    ### Overrides of base class methods ###

    def init(self):
        GStatus.init(self)
        self.mode = 'commit'
        self._last_commit_id = None

    def parse_opts(self):
        GStatus.parse_opts(self)

        # Need an entry, because extdiff code expects it
        if not self.test_opt('rev'):
            self.opts['rev'] = ''

        if self.test_opt('message'):
            buf = gtk.TextBuffer()
            buf.set_text(self.opts['message'])
            self.text.set_buffer(buf)

        if self.test_opt('logfile'):
            buf = gtk.TextBuffer()
            buf.set_text('Comment will be read from file ' + self.opts['logfile'])
            self.text.set_buffer(buf)
            self.text.set_sensitive(False)


    def get_title(self):
        root = os.path.basename(self.repo.root)
        user = self.opts.get('user')
        date = self.opts.get('date')
        pats = ' '.join(self.pats)
        return ' '.join([root, 'commit', pats, user, date])

    def get_icon(self):
        return 'menucommit.ico'

    def auto_check(self):
        if self.test_opt('check'):
            for entry in self.filemodel : 
                if entry[FM_STATUS] in 'MAR':
                    entry[FM_CHECKED] = True
            self._update_check_count()


    def save_settings(self):
        settings = GStatus.save_settings(self)
        settings['gcommit'] = self._vpaned.get_position()
        return settings


    def load_settings(self, settings):
        GStatus.load_settings(self, settings)
        if settings:
            self._setting_vpos = settings['gcommit']
        else:
            self._setting_vpos = -1


    def get_tbbuttons(self):
        tbbuttons = GStatus.get_tbbuttons(self)
        tbbuttons.insert(2, gtk.SeparatorToolItem())
        self._undo_button = self.make_toolbutton(gtk.STOCK_UNDO, _('_Undo'),
            self._undo_clicked, tip=_('undo recent commit'))
        self._commit_button = self.make_toolbutton(gtk.STOCK_OK, _('_Commit'),
            self._commit_clicked, tip=_('commit'))
        tbbuttons.insert(2, self._undo_button)
        tbbuttons.insert(2, self._commit_button)
        return tbbuttons


    def changed_cb(self, combobox):
        model = combobox.get_model()
        index = combobox.get_active()
        if index >= 0:
            buf = self.text.get_buffer()
            if buf.get_char_count() and buf.get_modified():
                response = Confirm(_('Discard Message'), [], self,
                        _('Discard current commit message?')).run()
                if response != gtk.RESPONSE_YES:
                    combobox.set_active(-1)
                    return
            buf.set_text(model[index][1])
            buf.set_modified(False)

    def _update_recent_messages(self, msg=None):
        if msg is not None:
            self._mru_messages.add(msg)
            self.settings.write()

        liststore = self.msg_cbbox.get_model()
        liststore.clear()
        for msg in self._mru_messages:
            sumline = msg.split("\n")[0]
            liststore.append([sumline, msg])
        #self.msg_cbbox.set_active(-1)

    def get_body(self):
        status_body = GStatus.get_body(self)

        vbox = gtk.VBox()
        
        mbox = gtk.HBox()

        label = gtk.Label(_('Branch: '))
        mbox.pack_start(label, False, False, 2)
        self.branchentry = gtk.Entry()
        mbox.pack_start(self.branchentry, False, False, 2)

        if hasattr(self.repo, 'mq'):
            label = gtk.Label('QNew: ')
            mbox.pack_start(label, False, False, 2)
            self.qnew_name = gtk.Entry()
            self.qnew_name.set_width_chars(6)
            self.qnew_name.connect('changed', self._qnew_changed)
            mbox.pack_start(self.qnew_name, False, False, 2)
        else:
            self.qnew_name = None

        label = gtk.Label(_('Recent Commit Messages: '))
        mbox.pack_start(label, False, False, 2)
        self.msg_cbbox = gtk.combo_box_new_text()
        liststore = gtk.ListStore(str, str)
        self.msg_cbbox = gtk.ComboBox(liststore)
        cell = gtk.CellRendererText()
        self.msg_cbbox.pack_start(cell, True)
        self.msg_cbbox.add_attribute(cell, 'text', 0)
        mbox.pack_start(self.msg_cbbox)
        vbox.pack_start(mbox, False, False)
        self._mru_messages = self.settings.mrul('recent_messages')
        self._update_recent_messages()
        self.msg_cbbox.connect('changed', self.changed_cb)
        
        frame = gtk.Frame()
        frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        frame.add(scroller)
        vbox.pack_start(frame)
        
        self.text = gtk.TextView()
        self.text.set_wrap_mode(gtk.WRAP_WORD)
        self.text.modify_font(pango.FontDescription(self.fontcomment))
        scroller.add(self.text)
        
        self._vpaned = gtk.VPaned()
        self._vpaned.add1(vbox)
        self._vpaned.add2(status_body)
        self._vpaned.set_position(self._setting_vpos)

        # make ctrl-o trigger commit button
        accel_group = gtk.AccelGroup()
        self.add_accel_group(accel_group)
        self._commit_button.add_accelerator("clicked", accel_group, ord("o"),
                              gtk.gdk.CONTROL_MASK, gtk.ACCEL_VISIBLE) 
        return self._vpaned


    def get_menu_info(self):
        """Returns menu info in this order: merge, addrem, unknown,
        clean, ignored, deleted
        """
        merge, addrem, unknown, clean, ignored, deleted, unresolved, resolved \
                = GStatus.get_menu_info(self)
        return (merge + (('_commit', self._commit_file),),
                addrem + (('_commit', self._commit_file),),
                unknown + (('_commit', self._commit_file),),
                clean,
                ignored,
                deleted + (('_commit', self._commit_file),),
                unresolved,
                resolved,
               )


    def should_live(self, widget=None, event=None):
        # If there are more than a few character typed into the commit
        # message, ask if the exit should continue.
        live = False
        buf = self.text.get_buffer()
        if buf.get_char_count() > 10 and buf.get_modified():
            dialog = Confirm(_('Exit'), [], self,
                    _('Save commit message at exit?'))
            res = dialog.run()
            if res == gtk.RESPONSE_YES:
                self._update_recent_messages(cur_msg)
            elif res != gtk.RESPONSE_NO:
                live = True
        if not live and self.main:
            self._destroying(widget)
        return live


    def reload_status(self):
        if not self._ready: return False
        success = GStatus.reload_status(self)
        self.branchentry.set_text(self.repo.dirstate.branch())
        self._check_merge()
        self._check_patch_queue()
        self._check_undo()
        return success


    ### End of overridable methods ###

    def _check_undo(self):
        can_undo = os.path.exists(self.repo.sjoin("undo")) and \
                self._last_commit_id is not None
        self._undo_button.set_sensitive(can_undo)


    def _check_merge(self):
        # disable the checkboxes on the filelist if repo in merging state
        merged = len(self.repo.changectx(None).parents()) > 1
        
        self.get_toolbutton(_('Re_vert')).set_sensitive(not merged)
        self.get_toolbutton(_('_Add')).set_sensitive(not merged)
        self.get_toolbutton(_('_Remove')).set_sensitive(not merged)
        self.get_toolbutton(_('Move')).set_sensitive(not merged)
        
        if merged:
            # select all changes if repo is merged
            for entry in self.filemodel:
                if entry[FM_STATUS] in 'MARD':
                    entry[FM_CHECKED] = True
            self._update_check_count()

            # pre-fill commit message
            buf = self.text.get_buffer()
            buf.set_text(_('merge'))
            buf.set_modified(False)
        #else:
        #    self.selectlabel.set_text(
        #        _('toggle change hunks to leave them out of commit'))



    def _check_patch_queue(self):
        '''See if an MQ patch is applied, switch to qrefresh mode'''
        mqmode = hasattr(self.repo, 'mq') and self.repo.mq.applied
        self.qheader = None
        if mqmode:
            patch = self.repo.mq.lookup('qtip')
            ph = self.repo.mq.readheaders(patch)
            title = os.path.basename(self.repo.root) + ' qrefresh ' + patch
            self.set_title(title)
            self.qheader = '\n'.join(ph.message)
            buf = self.text.get_buffer()
            if buf.get_char_count() == 0 or not buf.get_modified():
                buf.set_text(self.qheader)
                buf.set_modified(False)
            c_btn = self.get_toolbutton(_('_Commit'))
            c_btn.set_label(_('QRefresh'))
            c_btn.set_tooltip(self.tooltips, self.mqmode and _('QRefresh') or _('QNew'))
        else:
            c_btn = self.get_toolbutton(('_Commit'))
            c_btn.set_label(_('_Commit'))
            c_btn.set_tooltip(self.tooltips, _('commit'))
        self.branchentry.set_sensitive(not mqmode)

    def _commit_clicked(self, toolbutton, data=None):
        if not self._ready_message():
            return True

        if len(self.repo.changectx(None).parents()) > 1:
            # as of Mercurial 1.0, merges must be committed without
            # specifying file list.
            self._hg_commit([])
            shell_notify(self._relevant_files('MAR'))
            self.reload_status()
        else:
            commitable = 'MAR'
            addremove_list = self._relevant_files('?!')
            if len(addremove_list) and self._should_addremove(addremove_list):
                commitable += '?!'

            commit_list = self._relevant_files(commitable)
            if len(commit_list) > 0:
                self._commit_selected(commit_list)
            elif len(self.filemodel) == 0 and self._get_qnew_name():
                self._commit_selected([])
            else:
                Prompt('Nothing Commited', 'No committable files selected', self).run()
        return True

    def _commit_selected(self, files):
        # 1a. get list of chunks not rejected
        repo, chunks, ui = self.repo, self._shelve_chunks, self.ui
        model = self.diff_model
        files = [util.pconvert(f) for f in files]
        hlist = [x[DM_CHUNK_ID] for x in model if not x[DM_REJECTED]]

        # 2. backup changed files, so we can restore them in the end
        backups = {}
        backupdir = repo.join('record-backups')
        try:
            os.mkdir(backupdir)
        except OSError, err:
            if err.errno != errno.EEXIST:
                Prompt(_('Commit'), _('Unable to create ') + backupdir,
                        self).run()
                return
        try:
            # backup continues
            for f in files:
                if f not in self.modified: continue
                fh = self._filechunks.get(f)
                if not fh or len(fh) < 2: continue
                # unfiltered files do not go through backup-revert-patch cycle
                rejected = [x for x in fh[1:] if model[x][DM_REJECTED]]
                if len(rejected) == 0: continue
                fd, tmpname = tempfile.mkstemp(prefix=f.replace('/', '_')+'.',
                                               dir=backupdir)
                os.close(fd)
                ui.debug(_('backup %r as %r\n') % (f, tmpname))
                util.copyfile(repo.wjoin(f), tmpname)
                backups[f] = tmpname

            fp = cStringIO.StringIO()
            for n, c in enumerate(chunks):
                if c.filename() in backups and n in hlist:
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
                    ui.debug(_('applying patch\n'))
                    ui.debug(fp.getvalue())
                    pfiles = {}
                    patch.internalpatch(fp, ui, 1, repo.root, files=pfiles)
                    patch.updatedir(ui, repo, pfiles)
                except patch.PatchError, err:
                    s = str(err)
                    if s:
                        raise util.Abort(s)
                    else:
                        Prompt(_('Commit'), _('Unable to apply patch'), self).run()
                        raise util.Abort(_('patch failed to apply'))
            del fp

            # 4. We prepared working directory according to filtered patch.
            #    Now is the time to delegate the job to commit/qrefresh or the like!

            # it is important to first chdir to repo root -- we'll call a
            # highlevel command with list of pathnames relative to repo root
            cwd = os.getcwd()
            os.chdir(repo.root)
            try:
                self._hg_commit(files)
            finally:
                os.chdir(cwd)

            return 0
        finally:
            # 5. finally restore backed-up files
            try:
                for realname, tmpname in backups.iteritems():
                    ui.debug(_('restoring %r to %r\n') % (tmpname, realname))
                    util.copyfile(tmpname, repo.wjoin(realname))
                    os.unlink(tmpname)
                os.rmdir(backupdir)
            except OSError:
                pass
            self.reload_status()


    def _commit_file(self, stat, file):
        if self._ready_message():
            if stat not in '?!' or self._should_addremove([file]):
                self._hg_commit([file])
        return True


    def _undo_clicked(self, toolbutton, data=None):
        response = Confirm(_('Undo commit'), [], self, _('Undo last commit')).run() 
        if response != gtk.RESPONSE_YES:
            return
            
        tip = self._get_tip_rev(True)
        if not tip == self._last_commit_id:
            Prompt(_('Undo commit'), 
                    _('Unable to undo!\n\n'
                    'Tip revision differs from last commit.'),
                    self).run()
            return
            
        try:
            self.repo.rollback()
            self._last_commit_id = None
            self.reload_status()
        except:
            Prompt(_('Undo commit'), _('Errors during rollback!'), self).run()


    def _should_addremove(self, files):
        if self.test_opt('addremove'):
            return True
        else:
            response = Confirm(_('Add/Remove'), files, self).run() 
            if response == gtk.RESPONSE_YES:
                # This will stay set for further commits (meaning no more prompts). Problem?
                self.opts['addremove'] = True
                return True
        return False


    def _ready_message(self):
        if self.test_opt('logfile'):
            return
        buf = self.text.get_buffer()
        if buf.get_char_count() == 0:
            Prompt(_('Nothing Commited'),
                   _('Please enter commit message'), self).run()
            self.text.grab_focus()
            return False
        begin, end = buf.get_bounds()
        self.opts['message'] = buf.get_text(begin, end)
        return True


    def _hg_commit(self, files):
        if not self.repo.ui.config('ui', 'username'):
            Prompt(_('Commit: Invalid username'),
                   _('Your username has not been configured.\n\n'
                    'Please configure your username and try again'),
                    self).run()

            # bring up the config dialog for user to enter their username.
            # But since we can't be sure they will do it right, we will
            # have them to retry, to re-trigger the checking mechanism. 
            from thgconfig import ConfigDialog
            dlg = ConfigDialog(self.repo.root, False)
            dlg.show_all()
            dlg.focus_field('ui.username')
            dlg.run()
            dlg.hide()
            self.repo = hg.repository(ui.ui(), self.repo.root)
            self.ui = self.repo.ui
            return

        newbranch = fromutf(self.branchentry.get_text())
        if newbranch != self.repo.dirstate.branch():
            if newbranch in self.repo.branchtags():
                if newbranch not in [p.branch() for p in self.repo.parents()]:
                    response = Confirm(_('Override Branch'), [], self,
                        _('A branch named "%s" already exists,\n'
                        'override?') % newbranch).run()
                else:
                    response = gtk.RESPONSE_YES
            else:
                response = Confirm(_('New Branch'), [], self,
                        _('Create new named branch "%s"?') % newbranch).run()
            if response == gtk.RESPONSE_YES:
                self.repo.dirstate.setbranch(newbranch)
            elif response != gtk.RESPONSE_NO:
                return

        # call the threaded CmdDialog to do the commit, so the the large commit
        # won't get locked up by potential large commit. CmdDialog will also
        # display the progress of the commit operation.
        cmdline  = ['hg', 'commit', '--verbose', '--repository', self.repo.root]
        qnew = self._get_qnew_name()
        if qnew:
            qnew = fromutf(qnew)
            cmdline[1] = 'qnew'
            cmdline.append('--force')
        elif self.qheader is not None:
            cmdline[1] = 'qrefresh'
        if self.opts['addremove']:
            cmdline += ['--addremove']
        cmdline += ['--message', fromutf(self.opts['message'])]
        if qnew:
            cmdline += [qnew]
        cmdline += [self.repo.wjoin(x) for x in files]
        dialog = CmdDialog(cmdline, True)
        dialog.set_transient_for(self)
        dialog.run()
        dialog.hide()

        # refresh overlay icons and commit dialog
        if dialog.return_code() == 0:
            shell_notify([self.cwd] + files)
            buf = self.text.get_buffer()
            if buf.get_modified():
                self._update_recent_messages(self.opts['message'])
                buf.set_modified(False)
            if qnew:
                self.qnew_name.set_text('')
                self.repo.invalidate()
                _mq = self.repo.mq
                _mq.__init__(_mq.ui, _mq.basepath, _mq.path)
            elif self.qheader is None:
                self.text.set_buffer(gtk.TextBuffer())
                self._last_commit_id = self._get_tip_rev(True)

    def _get_tip_rev(self, refresh=False):
        if refresh:
            self.repo.invalidate()
        cl = self.repo.changelog
        tip = cl.node(nullrev + len(cl))
        return hex(tip)

    def _get_qnew_name(self):
        return self.qnew_name and self.qnew_name.get_text().strip() or ''

    def _qnew_changed(self, element):
        mqmode = self.mqmode
        self.mqmode = not self.qnew_name.get_text().strip()
        if mqmode != self.mqmode:
            c_btn = self.get_toolbutton(_('_Commit'))
            c_btn.set_label(self.mqmode and _('QRefresh') or _('QNew'))
            c_btn.set_tooltip(self.tooltips, self.mqmode and _('QRefresh') or _)('QNew')
            success, outtext = self._hg_call_wrapper('Status', self._do_reload_status)
            self.qnew_name.grab_focus() # set focus back
            

def launch(root='', files=[], cwd='', main=True):
    u = ui.ui()
    u.updateopts(debug=False, traceback=False)
    repo = hg.repository(u, path=root)
    
    # move cwd to repo root if repo is merged, so we can show
    # all the changed files
    if len(repo.changectx(None).parents()) > 1 and repo.root != cwd:
        cwd = repo.root
        repo = hg.repository(u, path=cwd)
        files = [cwd]

    ct = repo.ui.config('tortoisehg', 'extcommit', None)
    if ct == 'qct':
        from hglib import thgdispatch
        args = ['--repository', root, ct]
        try:
            thgdispatch(repo.ui, args=args)
        except SystemExit:
            pass
        return

    cmdoptions = {
        'user':'', 'date':'',
        'modified':True, 'added':True, 'removed':True, 'deleted':True,
        'unknown':True, 'ignored':False, 
        'exclude':[], 'include':[],
        'check': True, 'git':False, 'logfile':'', 'addremove':False,
    }
    
    dialog = GCommit(u, repo, cwd, files, cmdoptions, main)
    dialog.display()
    return dialog
    
def run(root='', files=[], cwd='', **opts):
    # If no files or directories were selected, take current dir
    # TODO: Not clear if this is best; user may expect repo wide
    if not files and cwd:
        files = [cwd]
    if launch(root, files, cwd, True):
        gtk.gdk.threads_init()
        gtk.gdk.threads_enter()
        gtk.main()
        gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    from hglib import rootpath

    opts = {}
    opts['cwd'] = len(sys.argv) > 1 and sys.argv[1] or os.getcwd()
    opts['root'] = rootpath(opts['cwd'])
    run(**opts)
