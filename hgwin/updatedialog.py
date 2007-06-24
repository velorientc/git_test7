"""
updatedialog.py - a simple update (chekcout) dialog for TortoiseHg

 Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.
"""

import win32ui
import win32con
from pywin.framework.dlgappcore import AppDialog
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

class UpdateDialog(AppDialog): 
    def __init__(self, path, revision="tip", title=None, tmpl=None):
        self.title = title
        self.path = path
        self.root = thgutil.find_root(path)
        if tmpl is None:
            tmpl = update_dlg_template()
        AppDialog.__init__(self, tmpl)
        self.AddDDX(win32ui.IDC_EDIT1, 'revision')
        self.data['revision']=revision
                
    def OnInitDialog(self): 
        rc = AppDialog.OnInitDialog(self)
        title = "hg update - %s" % self.root
        self.SetWindowText(title)

        # uncheck overwrite button        
        self.GetDlgItem(win32ui.IDC_CHECK1).SetCheck(0)
        self.data['overwrite']=0

    def OnOK(self):
        self._do_update()
        AppDialog.OnOK(self)

    def _do_update(self):
        rev = self.GetDlgItem(win32ui.IDC_EDIT1).GetWindowText()
        if rev.startswith("-"):
            rev = "-- " + rev
        clean = self.GetDlgItem(win32ui.IDC_CHECK1).GetCheck()

        cmdline = "hg --repository %s update --verbose %s %s" % (
                        util.shellquote(self.root),
                        clean and "--clean" or "",
                        rev)
        gpopen.run(cmdline, modal=True)

def do_update(path, title="Hg update"):
    dlg = UpdateDialog(path=path)
    dlg.CreateWindow()
    return dlg

if __name__ == "__main__":
    do_update("D:\\Profiles\\r28629\\My Documents\\Mercurial\\repos\\c1")
