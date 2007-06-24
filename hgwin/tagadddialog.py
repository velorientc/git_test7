"""
tagadddialog.py - TortoiseHg dialog to add tag to repository 

 Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.
"""

import win32ui
import win32con
from pywin.framework.dlgappcore import AppDialog
from mercurial import util
from mercurial.i18n import _
from mercurial.node import *
import gpopen
import thgutil

dlgStatic = 130
dlgEdit = 129
dlgButton = 128 

def error_dialog(msg):
    win32ui.MessageBox(msg, "hg tag", win32con.MB_OK | win32con.MB_ICONERROR)

def msg_dialog(msg):
    win32ui.MessageBox(msg, "hg tag", win32con.MB_OK)

def _dlg_template():
    w, h = 250, 100
    bw, bh = 40, 12
    e1w, e1h = 100, 12
    e2w, e2h = w-10, 24
    
    style = (#win32con.DS_MODALFRAME | 
             win32con.WS_POPUP | 
             win32con.WS_VISIBLE | 
             win32con.WS_CAPTION | 
             win32con.WS_SYSMENU |
             win32con.DS_CENTER |
             # win32con.DS_CENTERMOUSE |
             # win32con.WS_THICKFRAME |  # we can resize the dialog window
             win32con.DS_SETFONT)

    cs = win32con.WS_CHILD | win32con.WS_VISIBLE 
    s = win32con.WS_TABSTOP | cs 

    dlg = [["TortoiseHg", (3, 4, w, h), style, None, (8, "MS Sans Serif")],]
    
    dlg.append([dlgStatic, "Tag Name:", win32ui.IDC_PROMPT1, (5,9,40,12),
                    cs | win32con.SS_LEFT
               ])
    dlg.append([dlgEdit, "", win32ui.IDC_EDIT1, (50,6,e1w,e1h),
                    s | win32con.ES_AUTOHSCROLL | win32con.WS_BORDER
               ])
    dlg.append([dlgStatic, "Revision:", win32ui.IDC_PROMPT2, (5,26,40,12),
                    cs | win32con.SS_LEFT
               ])
    dlg.append([dlgEdit, "tip", win32ui.IDC_EDIT2, (50,25,e1w,e1h),
                    s | win32con.ES_AUTOHSCROLL | win32con.WS_BORDER
               ])
    dlg.append([dlgButton,"Create local tag", win32ui.IDC_CHECK1, (50,40,100,12),
                    s | win32con.BS_AUTOCHECKBOX
               ])
    #dlg.append([dlgStatic, "Commit Message:", win32ui.IDC_PROMPT3, (5,65,60,10),
    #                cs | win32con.SS_LEFT
    #           ])
    dlg.append([dlgButton,"Use commit message:", win32ui.IDC_CHECK2, (5,h-e2h-5-12,100,12),
                    s | win32con.BS_AUTOCHECKBOX
               ])
    dlg.append([dlgEdit, "", win32ui.IDC_EDIT3, (5,h-e2h-5,e2w,e2h),
                    s | win32con.SS_LEFT
                      | win32con.WS_BORDER
                     # | win32con.ES_MULTILINE
                     # | win32con.WS_VSCROLL
                      | win32con.WS_HSCROLL
                     # | win32con.ES_WANTRETURN
                      | win32con.ES_READONLY
               ])
    dlg.append([dlgButton,"OK", win32con.IDOK, (w-bw-5,5,bw,bh),
                    s | win32con.BS_PUSHBUTTON
               ]) 
    dlg.append([dlgButton,"Cancel", win32con.IDCANCEL, (w-bw-5,20,bw,bh),
                    s | win32con.BS_PUSHBUTTON
               ]) 
    dlg.append([dlgButton,"Tags", win32ui.IDC_BUTTON1, (w-bw-5,35,bw,bh),
                    s | win32con.BS_PUSHBUTTON
               ]) 
    return dlg

class AddTagDialog(AppDialog): 
    def __init__(self, path, revision="tip", title=None):
        self.title = title
        self.path = path
        self.root = thgutil.find_root(path)
        tmpl = _dlg_template()
        AppDialog.__init__(self, tmpl)
        self.AddDDX(win32ui.IDC_EDIT2, 'revision')
        self.data['revision']=revision
                
    def OnInitDialog(self): 
        rc = AppDialog.OnInitDialog(self)

        # setup control handlers        
        self.HookCommand(self.OnNotify, win32ui.IDC_CHECK2)
        self.HookCommand(self.OnNotify, win32ui.IDC_BUTTON1)

        # set dialog title
        title = "hg tag - %s" % self.root
        self.SetWindowText(title)

    def OnOK(self):
        if self._add_tag() == True:
            AppDialog.OnOK(self)

    def _add_tag(self):
        # read input
        name = self.GetDlgItem(win32ui.IDC_EDIT1).GetWindowText()
        rev = self.GetDlgItem(win32ui.IDC_EDIT2).GetWindowText()
        local = self.GetDlgItem(win32ui.IDC_CHECK1).GetCheck()

        message = None        
        if self.GetDlgItem(win32ui.IDC_CHECK2).GetCheck():
            message = self.GetDlgItem(win32ui.IDC_EDIT3).GetWindowText()

        # verify input
        if name == "":
            error_dialog("Please enter tag name")
            return False
        if rev == "":
            error_dialog("Pleas enter revision to tag")
            return False

        # add tag to repo        
        try:
            self._add_hg_tag(name, rev, message, local)
        except util.Abort, inst:
            error_dialog("Error: %s" % inst)
            return False
        except:
            error_dialog("Unknown wrror when adding tag")
            raise
            return False

        return True
    
    def _add_hg_tag(self, name, revision, message, local, user=None,
                    date=None, force=False):
        root = thgutil.find_root(self.path)
        u = ui.ui()
        try:
            repo = hg.repository(u, path=root)
        except repo.RepoError:
            return None

        if name in repo.tags() and not force:
            raise util.Abort(_('a tag named "%s" already exists')
                             % name)
        r = repo.changectx(revision).node()

        if not message:
            message = _('Added tag %s for changeset %s') % (name, short(r))

        repo.tag(name, r, message, local, user, date)

    def OnNotify(self, id, code):
        if id == win32ui.IDC_CHECK2:
            state = self.GetDlgItem(win32ui.IDC_CHECK2).GetCheck()
            self.GetDlgItem(win32ui.IDC_EDIT3).SetReadOnly(state == False)
        elif id == win32ui.IDC_BUTTON1:
            import taglistdialog
            dlg = taglistdialog.TagsDialog(self.root)
            dlg.CreateWindow()

def test(path):
    dlg = AddTagDialog(path=path)
    dlg.CreateWindow()
    return dlg

if __name__ == "__main__":
    test("c:\\hg\\h1")
