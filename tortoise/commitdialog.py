"""
commitdialog.py - a simple commit dialog for TortoiseHg

 Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.
"""

import os, tempfile, re
import win32ui
import win32con
from pywin.mfc import dialog
from mercurial import hg, repo, ui, cmdutil, util
import gpopen
import thgutil

def get_changes_text(filenames):
    root = thgutil.find_root(filenames[0])
    u = ui.ui()
    try:
        repo = hg.repository(u, path=root)
    except repo.RepoError:
        return None
    
    # get file status
    try:
        files, matchfn, anypats = cmdutil.matchpats(repo, filenames)
        modified, added, removed, deleted, unknown, ignored, clean = [
                n for n in repo.status(files=files, list_clean=False)]
    except util.Abort, inst:
        return None

    if not (modified + added + removed):
        return None
    
    edittext = []
    edittext.append("")
    edittext.append("HG: user: %s" % u.username())
    edittext.extend(["HG: changed %s" % f for f in modified])
    edittext.extend(["HG: removed %s" % f for f in removed])
    edittext.extend(["HG: Added %s" % f for f in added])
    edittext.append("")

    return "\n".join(edittext)

class SimpleCommitDialog(dialog.Dialog):
    def __init__(self, files=[], title="Mercurial: commit"):
        self.title = title
        self.commitfiles = files
        dialog.Dialog.__init__(self, win32ui.IDD_LARGE_EDIT)

    def OnInitDialog(self):
        self.SetWindowText(self.title)

        cancel=self.GetDlgItem(win32con.IDCANCEL)
        cancel.ShowWindow(win32con.SW_SHOW)
        
        okBtn = self.GetDlgItem(win32con.IDOK)
        okBtn.SetWindowText("Commit")

        self.font = win32ui.CreateFont({'name': "Courier New", 'height': 14})
        edit = self.GetDlgItem(win32ui.IDC_EDIT1)
        edit.SetFont(self.font)

        # get the list of changes to present at the editor
        text = get_changes_text(self.commitfiles)
        if text:
            text = text.replace("\n", "\r\n")
            edit.SetWindowText(text)
        else:
            edit.SetWindowText("<<No changes to commit>>")
            edit.EnableWindow(False)
            okBtn.EnableWindow(False)

    def OnOK(self):
        if self._do_commit() == True:
            dialog.Dialog.OnOK(self)
        
    def _do_commit(self):
        # strip log message of lines with HG: prefix
        text = self.GetDlgItem(win32ui.IDC_EDIT1).GetWindowText()
        text = re.sub("(?m)^HG:.*\r\n", "", text)
        lines = [line.rstrip() for line in text.rstrip().splitlines()]
        while lines and not lines[0]:
            del lines[0]
        if not lines:
            win32ui.MessageBox("Commit message is empty!", "Mercurial",
                               win32con.MB_OK | win32con.MB_ICONERROR)
            return False
        
        # save log message to a temp file        
        text = '\n'.join(lines)
        logfd, logpath = tempfile.mkstemp(prefix="tortoisehg_ci_log_")
        os.write(logfd, text)
        os.close(logfd)

        # commit file with log message        
        root = thgutil.find_root(self.commitfiles[0])
        quoted_files = [util.shellquote(s) for s in self.commitfiles]
        cmdline = "hg --repository %s commit --verbose --logfile %s %s" % (
                        util.shellquote(root),
                        util.shellquote(logpath),
                        " ".join(quoted_files))
        gpopen.run(cmdline, modal=True)
        os.unlink(logpath)
        
        # refresh overlay icons in commit directories
        # FIXME: other explorer windows opened on the same repo
        #        may not get refreshed
        for f in self.commitfiles:
            dir = os.path.isdir(f) and f or os.path.dirname(f)
            thgutil.shell_notify(dir)

        return True

def do_commit(files):
    """
    show a simple editor dialog for enter log message,
    and commit the list of files.
    """

    # show commit dialog
    dlg = SimpleCommitDialog(files=files)
    dlg.CreateWindow()
    return dlg

if __name__ == "__main__":
    files = ["D:\\Profiles\\r28629\\My Documents\\Mercurial\\repos\\c1\\"]
    do_commit(files)
