# statusact.py - actions for status dialog for TortoiseHg
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2008 Steve Borho <steve@borho.org>
# Copyright 2008 Emmanuel Rosa <goaway1000@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk

from mercurial import commands

from tortoisehg.util import hglib, shlib
from tortoisehg.util.i18n import _

from tortoisehg.hgtk import dialog, gdialog, gtklib


class statusact(object):

    def __init__(self, stat):
        self.stat = stat

    def rename_file(self, wfile):
        fdir, fname = os.path.split(wfile)
        utf_fname = hglib.toutf(fname)
        newfile = dialog.entry_dialog(self.stat, _('Rename file to:'),
                         True, utf_fname)
        if newfile and newfile != utf_fname:
            self.hg_move([wfile, os.path.join(fdir, hglib.fromutf(newfile))])
        return True


    def copy_file(self, wfile):
        wfile = self.stat.repo.wjoin(wfile)
        fdir, fname = os.path.split(wfile)
        result = gtklib.NativeSaveFileDialogWrapper(title=_('Copy file to'),
                                                    initial=fdir,
                                                    filename=fname).run()
        if not result:
            return
        if result != wfile:
            self.hg_copy([wfile, result])
        return True


    def hg_remove(self, files):
        wfiles = [self.stat.repo.wjoin(x) for x in files]
        if self.stat.count_revs() > 1:
            gdialog.Prompt(_('Nothing Removed'),
              _('Remove is not enabled when multiple revisions are specified.'),
              self.stat).run()
            return

        # Create new opts, so nothing unintented gets through
        removeopts = self.stat.merge_opts(commands.table['^remove|rm'][1],
                                     ('include', 'exclude'))
        def dohgremove():
            commands.remove(self.stat.ui, self.stat.repo, *wfiles, **removeopts)
        success, outtext = self.stat._hg_call_wrapper('Remove', dohgremove)
        if success:
            self.stat.reload_status()


    def hg_move(self, files):
        wfiles = [self.stat.repo.wjoin(x) for x in files]
        if self.stat.count_revs() > 1:
            gdialog.Prompt(_('Nothing Moved'), _('Move is not enabled when '
                    'multiple revisions are specified.'), self.stat).run()
            return

        # Create new opts, so nothing unintented gets through
        moveopts = self.stat.merge_opts(commands.table['rename|mv'][1],
                ('include', 'exclude'))
        def dohgmove():
            #moveopts['force'] = True
            commands.rename(self.stat.ui, self.stat.repo, *wfiles, **moveopts)
        success, outtext = self.stat._hg_call_wrapper('Move', dohgmove)
        if success:
            self.stat.reload_status()


    def hg_copy(self, files):
        wfiles = [self.stat.repo.wjoin(x) for x in files]
        if self.stat.count_revs() > 1:
            gdialog.Prompt(_('Nothing Copied'), _('Copy is not enabled when '
                    'multiple revisions are specified.'), self).run()
            return

        # Create new opts, so nothing unintented gets through
        cmdopts = self.stat.merge_opts(commands.table['copy|cp'][1],
                ('include', 'exclude'))
        def dohgcopy():
            commands.copy(self.stat.ui, self.stat.repo, *wfiles, **cmdopts)
        success, outtext = self.stat._hg_call_wrapper('Copy', dohgcopy)
        if success:
            self.stat.reload_status()


    def hg_revert(self, files):
        wfiles = [self.stat.repo.wjoin(x) for x in files]
        if self.stat.count_revs() > 1:
            gdialog.Prompt(_('Nothing Reverted'),
                   _('Revert not allowed when viewing revision range.'),
                   self.stat).run()
            return

        # Create new opts,  so nothing unintented gets through.
        revertopts = self.stat.merge_opts(commands.table['revert'][1],
                                     ('include', 'exclude', 'rev'))
        def dohgrevert():
            commands.revert(self.stat.ui, self.stat.repo, *wfiles, **revertopts)

        def filelist(files):
            text = '\n'.join(files[:5])
            if len(files) > 5:
                text += '  ...\n'
            return hglib.toutf(text)

        if self.stat.is_merge():
            res = gdialog.CustomPrompt(
                    _('Uncommited merge - please select a parent revision'),
                    _('Revert files to local or other parent?'),
                    self.stat, (_('&Local'), _('&Other'), _('&Cancel')), 2).run()
            if res == 0:
                revertopts['rev'] = self.stat.repo[None].p1().rev()
            elif res == 1:
                revertopts['rev'] = self.stat.repo[None].p2().rev()
            else:
                return
            response = None
        else:
            # response: 0=Yes, 1=Yes,no backup, 2=Cancel
            revs = revertopts['rev']
            if revs and type(revs) == list:
                revertopts['rev'] = revs[0]
                msg = _('Revert files to revision %s?') % revs[0]
            else:
                revertopts['rev'] = '.'
                msg = _('Revert files?')
            msg += '\n\n'
            msg += filelist(files)
            response = gdialog.CustomPrompt(_('Confirm Revert'), msg,
                    self.stat, (_('&Yes (backup changes)'),
                    _('Yes (&discard changes)'), _('&Cancel')), 2, 2).run()
        if response in (None, 0, 1):
            if response == 1:
                revertopts['no_backup'] = True
            success, outtext = self.stat._hg_call_wrapper('Revert', dohgrevert)
            if success:
                shlib.shell_notify(wfiles)
                self.stat.reload_status()


    def hg_forget(self, files):
        wfiles = [self.stat.repo.wjoin(x) for x in files]
        commands.forget(self.stat.ui, self.stat.repo, *wfiles)
        self.stat.reload_status()


    def hg_add(self, files):
        wfiles = [self.stat.repo.wjoin(x) for x in files]
        # Create new opts, so nothing unintented gets through
        addopts = self.stat.merge_opts(commands.table['^add'][1],
                                  ('include', 'exclude'))
        def dohgadd():
            commands.add(self.stat.ui, self.stat.repo, *wfiles, **addopts)
        success, outtext = self.stat._hg_call_wrapper('Add', dohgadd)
        if success:
            shlib.shell_notify(wfiles)
            self.stat.reload_status()


    def delete_files(self, files):
        dlg = gdialog.Confirm(_('Confirm Delete Unrevisioned'), files, self.stat,
                _('Delete the following unrevisioned files?'))
        if dlg.run() == gtk.RESPONSE_YES:
            errors = ''
            for wfile in files:
                try:
                    os.unlink(self.stat.repo.wjoin(wfile))
                except Exception, inst:
                    errors += str(inst) + '\n\n'

            if errors:
                errors = errors.replace('\\\\', '\\')
                if len(errors) > 500:
                    errors = errors[:errors.find('\n',500)] + '\n...'
                gdialog.Prompt(_('Delete Errors'), errors, self.stat).run()

            self.stat.reload_status()
        return True
