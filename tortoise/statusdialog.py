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
    def __init__(self, title, hierList, bitmapID = win32ui.IDB_HIERFOLDERS,
                 dlgID = win32ui.IDD_TREE, dll = None, 
                 childListBoxID = win32ui.IDC_LIST1):
        hierlist.HierDialog.__init__(self, title, hierList, bitmapID,
                                     self._dialog_template(), dll,
                                     childListBoxID)

    # support dialog app
    def PreDoModal(self):
        pass
    
    def _dialog_template(self):
        # dialog resource reference:
        #
        # IDD_TREE DIALOG DISCARDABLE  0, 0, 226, 93
        # STYLE DS_MODALFRAME | WS_POPUP | WS_VISIBLE | WS_CAPTION | WS_SYSMENU
        # CAPTION "title"
        # FONT 8, "MS Sans Serif"
        # BEGIN
        #     DEFPUSHBUTTON   "OK",IDOK,170,5,50,14
        #     PUSHBUTTON      "Cancel",IDCANCEL,170,25,50,14
        #     CONTROL         "Tree1",IDC_LIST1,"SysTreeView32",TVS_HASBUTTONS | 
        #                    TVS_HASLINES | TVS_LINESATROOT | TVS_SHOWSELALWAYS | 
        #                    WS_BORDER | WS_TABSTOP,3,3,160,88
        # END
        
        style = (win32con.DS_MODALFRAME | 
                 win32con.WS_POPUP | 
                 win32con.WS_VISIBLE | 
                 win32con.WS_CAPTION | 
                 win32con.WS_SYSMENU |
                 win32con.DS_CENTER |
                 win32con.DS_CENTERMOUSE |
                 #win32con.WS_THICKFRAME |  # we can resize the dialog window
                 win32con.DS_SETFONT)

        cs = win32con.WS_CHILD | win32con.WS_VISIBLE 
        s = win32con.WS_TABSTOP | cs 

        dlg = [["TortoiseHg", (0, 0, 226, 93), style, None, (8, "MS Sans Serif")],]
        
        dlg.append(['SysTreeView32', "Tree1", win32ui.IDC_LIST1, (3,3,160,88),
                        s | win32con.WS_BORDER
                          | win32con.WS_CHILD
                          | win32con.WS_VISIBLE
                          | commctrl.TVS_HASBUTTONS
                          | commctrl.TVS_HASLINES
                          | commctrl.TVS_LINESATROOT
                          | commctrl.TVS_SHOWSELALWAYS
                   ])
        dlg.append([128 ,"OK", win32con.IDOK, (170,5,50,14),
                        s | win32con.BS_PUSHBUTTON
                   ]) 
        dlg.append([128,"Cancel", win32con.IDCANCEL, (170,25,50,14),
                        s | win32con.BS_PUSHBUTTON
                   ]) 
        return dlg

def status_dialog(root, files=[]):
    stlist = HgStatusList(root, files)
    dlg = StatusDialog('hg status - %s' % root, stlist)
    return dlg

def test(root, files=[]):
    dlg = status_dialog(root, files)
    dlg.CreateWindow()

if __name__=='__main__':
    test("c:\hg\h1")
    #test("c:\hg\h1", ["c:\hg\h1\mercurial"])