"""
updatedialog.py - a simple update (chekcout) dialog for TortoiseHg

 Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.
"""

import win32ui
import win32con
from pywin.mfc.dialog import Dialog
from mercurial import util
import gpopen
import thgutil

dlgStatic = 130
dlgEdit = 129
dlgButton = 128 

def update_dlg_template():
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

    dlg = [["TortoiseHg", (3, 4, 219, 46), style, None, (8, "MS Sans Serif")],]
    
    dlg.append([dlgStatic, "Revision:", win32ui.IDC_PROMPT1, (5,8,40,12),
                    cs | win32con.SS_LEFT
               ])
    dlg.append([dlgEdit, "tip", win32ui.IDC_EDIT1, (50,6,80,12),
                    s | win32con.ES_AUTOHSCROLL | win32con.WS_BORDER
               ])
    dlg.append([dlgButton,"Overwrite local changes", win32ui.IDC_CHECK1, (50,25,100,12),
                    s | win32con.BS_AUTOCHECKBOX
               ])
    dlg.append([dlgButton,"OK", win32con.IDOK, (171,5,40,15),
                    s | win32con.BS_PUSHBUTTON
               ]) 
    dlg.append([dlgButton,"Cancel", win32con.IDCANCEL, (171,23,40,14),
                    s | win32con.BS_PUSHBUTTON
               ]) 
    return dlg

class UpdateDialog(Dialog): 
    def __init__(self, revision="tip", title=None, tmpl=None):
        self.title = title
        if tmpl is None:
            tmpl = update_dlg_template()
        Dialog.__init__(self, tmpl)
        self.AddDDX(win32ui.IDC_EDIT1, 'revision')
        self.data['revision']=revision
                
    def OnInitDialog(self): 
        rc = Dialog.OnInitDialog(self)
        self.SetWindowText(self.title)

        # uncheck overwrite button        
        self.GetDlgItem(win32ui.IDC_CHECK1).SetCheck(0)
        self.data['overwrite']=0

    def OnOK(self):
        chbox = self.GetDlgItem(win32ui.IDC_CHECK1)
        self.data['overwrite'] = chbox.GetCheck()
        Dialog.OnOK(self)

def do_update(path, title="Hg update"):
    dlg = UpdateDialog(title=title)
    if dlg.DoModal() == win32con.IDOK:
        rev = dlg['revision']
        if rev.startswith("-"):
            rev = "-- " + rev
        clean = dlg['overwrite']
        root = thgutil.find_root(path)
        cmdline = "hg --repository %s update --verbose %s %s" % (
                        util.shellquote(root),
                        clean and "--clean" or "",
                        rev)
        gpopen.run(cmdline, title=title, modal=True)
        return True
    return False

if __name__ == "__main__":
    do_update("D:\\Profiles\\r28629\\My Documents\\Mercurial\\repos\\c1")
