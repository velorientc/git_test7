"""
statusdialog.py - a simple status dialog for TortoiseHg

 Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.
"""
import win32ui
import os
import commctrl
from pywin.tools import hierlist
from mercurial import hg, repo, ui, cmdutil, util
import thgutil

def get_repo_status(root, files=[], list_clean=False):
    u = ui.ui()
    try:
        repo = hg.repository(u, path=root)
    except repo.RepoError:
        return None

    # get file status
    try:
        files, matchfn, anypats = cmdutil.matchpats(repo, pats=files)
        modified, added, removed, deleted, unknown, ignored, clean = [
                n for n in repo.status(files=files, list_clean=list_clean)]
    except util.Abort, inst:
        return None

    return {'modified': modified,
            'added': added,
            'removed': removed,
            'deleted': deleted,
            'unknown': unknown,
            'ignored': ignored,
            'clean': clean}

class HgStatusList(hierlist.HierList):
    def __init__(self, root, files=[], listBoxID = win32ui.IDC_LIST1):
        hierlist.HierList.__init__(self, root, win32ui.IDB_HIERFOLDERS, listBoxID)
        self.status = get_repo_status(root, files=files)

    def GetText(self, item):
        return os.path.normpath(item)

    def GetSubList(self, item):
        if item == self.root:
            ret = [x for x in self.status.keys() if self.status[x]]
        elif self.status.has_key(item):
            ret = self.status[item]
        else:
            ret = None
        return ret

    def IsExpandable(self, item):
        return self.status.has_key(item)

    def GetSelectedBitmapColumn(self, item):
        return self.GetBitmapColumn(item)+6 # Use different color for selection

    def OnTreeItemDoubleClick(self,(hwndFrom, idFrom, code), extra):
        pass

class StatusDialog(hierlist.HierDialog):
    # support dialog app
    def PreDoModal(self):
        pass
        
def status_dialog(root, files=[]):
    stlist = HgStatusList(root, files)
    dlg = StatusDialog('hg status - %s' % root, stlist)
    return dlg

def test(root, files=[]):
    dlg = status_dialog(root, files)
    dlg.CreateWindow()

if __name__=='__main__':
    test("c:\hg\h1")
    test("c:\hg\h1", ["c:\hg\h1\mercurial"])