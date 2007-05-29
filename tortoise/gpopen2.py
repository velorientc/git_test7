#
# Execute a Mercurial (Hg) command and show it's output on an win32gui dialog.
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#
import os, sys
import winxpgui as win32gui
import win32api
import win32con
import struct
import commctrl
import subprocess
import getopt
import thgutil

# control ID
IDC_COMMANDTEXT = 1024
IDC_BUTTON_REFRESH = 1025
IDC_BUTTON_CLOSE = 1026
IDC_OUTPUT_EDIT = 1027

g_registeredClass = 0

def getIconPath(*args):
    icon = os.path.join(os.path.dirname(__file__), "..", "icons", *args)
    if not os.path.isfile(icon):
        return None
    return icon

def setEditFont(hwnd, fontname, height):
    lf = win32gui.LOGFONT()
    lf.lfFaceName = fontname
    lf.lfHeight = height
    #lf.lfWidth = width
    #lf.lfPitchAndFamily = win32con.FIXED_PITCH
    font = win32gui.CreateFontIndirect(lf)
    win32gui.SendMessage(hwnd, win32con.WM_SETFONT, font, 0)
    return font

def setEditText(hwnd, text, append=False):
    text = type(text) == type([]) and text or [text]
    
    # Set the current selection range, depending on append flag
    if append:
        win32gui.SendMessage(hwnd, win32con.EM_SETSEL, -1, 0)
    else:
        win32gui.SendMessage(hwnd, win32con.EM_SETSEL, 0, -1)

    # Send the text
    win32gui.SendMessage(hwnd,
                         win32con.EM_REPLACESEL,
                         True,
                         os.linesep.join(text))

class PopenWindowBase:
    def __init__(self):
        win32gui.InitCommonControls()
        self.hinst = win32gui.dllhandle
        self.list_data = {}

    def CreateWindow(self):
        self._isModal = False
        self._DoCreate(win32gui.CreateDialogIndirect)
        
    def DoModal(self):
        self._isModal = True
        return self._DoCreate(win32gui.DialogBoxIndirect)

    def _RegisterWndClass(self):
        className = "TortoiseHgDialog"
        global g_registeredClass
        if not g_registeredClass:
            message_map = {}
            wc = win32gui.WNDCLASS()
            wc.SetDialogProc() # Make it a dialog class.
            wc.hInstance = self.hinst
            wc.lpszClassName = className
            wc.style = win32con.CS_VREDRAW | win32con.CS_HREDRAW
            wc.hCursor = win32gui.LoadCursor( 0, win32con.IDC_ARROW )
            wc.hbrBackground = win32con.COLOR_WINDOW + 1
            wc.lpfnWndProc = message_map # could also specify a wndproc.
            # C code: wc.cbWndExtra = DLGWINDOWEXTRA + sizeof(HBRUSH) + (sizeof(COLORREF));
            wc.cbWndExtra = win32con.DLGWINDOWEXTRA + struct.calcsize("Pi")
            icon_flags = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
            icon_path = getIconPath("tortoise", "hg.ico")
            if icon_path:
                wc.hIcon = win32gui.LoadImage(self.hinst, icon_path,
                                              win32con.IMAGE_ICON,
                                              0,
                                              0,
                                              icon_flags)
            classAtom = win32gui.RegisterClass(wc)
            g_registeredClass = 1
        return className

    def _GetDialogTemplate(self, dlgClassName):
        w = 300
        h = 250
        style = (  win32con.WS_THICKFRAME 
                 | win32con.WS_POPUP 
                 | win32con.WS_VISIBLE 
                 | win32con.WS_CAPTION 
                 | win32con.WS_SYSMENU 
                 | win32con.DS_SETFONT 
                 | win32con.WS_MINIMIZEBOX )
        cs = win32con.WS_CHILD | win32con.WS_VISIBLE
        title = "Mercurial"

        # Window frame and title
        dlg = [ [title, (0, 0, w, h), style, None, (8, "MS Sans Serif"),
                 None, dlgClassName], ]

        # ID label and text box
        dlg.append([130, "Command:", -1, (5, 5, w - 10, 9), cs | win32con.SS_LEFT])
        s = cs | win32con.WS_TABSTOP | win32con.WS_BORDER
        dlg.append(['EDIT', None, IDC_COMMANDTEXT, (5, 15, w - 10, 12), s])

        # Search/Display Buttons
        # (x positions don't matter here)
        s = cs | win32con.WS_TABSTOP
        dlg.append([128, "Refresh", IDC_BUTTON_REFRESH, (5, 35, 50, 14), s])
        dlg.append([128, "Close", IDC_BUTTON_CLOSE, (100, 35, 50, 14), 
                    s | win32con.BS_DEFPUSHBUTTON])

        dlg.append(['EDIT', "", IDC_OUTPUT_EDIT, (5, 55, w - 10, h - 60),
                    cs | win32con.SS_LEFT
                       | win32con.WS_BORDER
                       | win32con.ES_MULTILINE
                       | win32con.WS_VSCROLL
                       | win32con.WS_HSCROLL
                       | win32con.ES_WANTRETURN
                   ])
        return dlg

    def _DoCreate(self, fn):
        message_map = {
            win32con.WM_SIZE: self.OnSize,
            win32con.WM_COMMAND: self.OnCommand,
            win32con.WM_NOTIFY: self.OnNotify,
            win32con.WM_INITDIALOG: self.OnInitDialog,
            win32con.WM_CLOSE: self.OnClose,
            win32con.WM_DESTROY: self.OnDestroy,
        }
        dlgClassName = self._RegisterWndClass()
        template = self._GetDialogTemplate(dlgClassName)
        return fn(self.hinst, template, 0, message_map)

    def OnInitDialog(self, hwnd, msg, wparam, lparam):
        self.hwnd = hwnd
        # centre the dialog
        desktop = win32gui.GetDesktopWindow()
        l,t,r,b = win32gui.GetWindowRect(self.hwnd)
        dt_l, dt_t, dt_r, dt_b = win32gui.GetWindowRect(desktop)
        centre_x, centre_y = win32gui.ClientToScreen( desktop, ( (dt_r-dt_l)/2, (dt_b-dt_t)/2) )
        win32gui.MoveWindow(hwnd, centre_x-(r/2), centre_y-(b/2), r-l, b-t, 0)
        l,t,r,b = win32gui.GetClientRect(self.hwnd)
        self._DoSize(r-l,b-t, 1)

    def _DoSize(self, cx, cy, repaint = 1):
        # right-justify the textbox.
        ctrl = win32gui.GetDlgItem(self.hwnd, IDC_COMMANDTEXT)
        l, t, r, b = win32gui.GetWindowRect(ctrl)
        l, t = win32gui.ScreenToClient(self.hwnd, (l,t) )
        r, b = win32gui.ScreenToClient(self.hwnd, (r,b) )
        win32gui.MoveWindow(ctrl, l, t, cx-l-5, b-t, repaint)

        # The button.
        ctrl = win32gui.GetDlgItem(self.hwnd, IDC_BUTTON_CLOSE)
        l, t, r, b = win32gui.GetWindowRect(ctrl)
        l, t = win32gui.ScreenToClient(self.hwnd, (l,t) )
        r, b = win32gui.ScreenToClient(self.hwnd, (r,b) )
        list_y = b + 10
        w = r - l
        win32gui.MoveWindow(ctrl, cx - 5 - w, t, w, b-t, repaint)

        # the output textbox
        ctrl = win32gui.GetDlgItem(self.hwnd, IDC_OUTPUT_EDIT)
        l, t, r, b = win32gui.GetWindowRect(ctrl)
        l, t = win32gui.ScreenToClient(self.hwnd, (l,t) )
        r, b = win32gui.ScreenToClient(self.hwnd, (r,b) )
        w = r - l
        win32gui.MoveWindow(ctrl, l, t, cx -l -5, cy -t -5, repaint)

    def OnSize(self, hwnd, msg, wparam, lparam):
        x = win32api.LOWORD(lparam)
        y = win32api.HIWORD(lparam)
        self._DoSize(x,y)
        return 1

    def OnNotify(self, hwnd, msg, wparam, lparam):
        format = "iiiiiiiiiii"
        buf = win32gui.PyMakeBuffer(struct.calcsize(format), lparam)
        hwndFrom, idFrom, code, iItem, iSubItem, uNewState, uOldState, uChanged, actionx, actiony, lParam \
                  = struct.unpack(format, buf)
        # *sigh* - work around a problem with old commctrl modules, which had a
        # bad value for PY_OU, which therefore cause most "control notification"
        # messages to be wrong.
        # Code that needs to work with both pre and post pywin32-204 must do
        # this too.
        code += commctrl.PY_0U
        if code == commctrl.NM_DBLCLK:
            print "Double click on item", iItem+1
        return 1

    def OnCommand(self, hwnd, msg, wparam, lparam):
        id = win32api.LOWORD(wparam)
        if id == IDC_BUTTON_REFRESH:
            self.DoRefresh()
        elif id == IDC_BUTTON_CLOSE:
            self.DoClose()

    def DoRefresh(self):
        pass

    def DoClose(self):
        self._do_close(self.hwnd)

    def _do_close(self, hwnd):
        if self._isModal:
            win32gui.EndDialog(hwnd, 0)
        else:
            win32gui.DestroyWindow(hwnd)
    
    def OnClose(self, hwnd, msg, wparam, lparam):
        self._do_close(hwnd)

    def OnDestroy(self, hwnd, msg, wparam, lparam):
        self._do_close(hwnd)

class PopenDialog(PopenWindowBase):
    def __init__(self, cmdline='', title="popen"):
        self.cmdline = cmdline
        self.title = title
        self.outbuf = ""
        PopenWindowBase.__init__(self)

    def OnInitDialog(self, hwnd, msg, wparam, lparam):
        rc = PopenWindowBase.OnInitDialog(self, hwnd, msg, wparam, lparam)
        self._setup_dialog()

    def _setup_dialog(self):
        win32gui.SetWindowText(self.hwnd, self.title)
        ctrl = win32gui.GetDlgItem(self.hwnd, IDC_COMMANDTEXT)
        cmdline = type(self.cmdline) == type([]) and " ".join(self.cmdline) \
                                                  or self.cmdline
        setEditText(ctrl, cmdline)
        win32gui.SendMessage(ctrl, win32con.EM_SETREADONLY, 1, 0);
        
        # condition output text control
        self.outtext = win32gui.GetDlgItem(self.hwnd, IDC_OUTPUT_EDIT)
        win32gui.SendMessage(self.outtext, win32con.EM_LIMITTEXT, 100000000, 0);
        win32gui.SendMessage(self.outtext, win32con.EM_SETREADONLY, 1, 0);
        self.fixedfont = setEditFont(self.outtext, "Courier New", 15)
        #win32gui.SetTextColor(self.outtext, win32api.RGB(255,0,0))
        
        self._start_thread()

    # We need to arrange to a WM_QUIT message to be sent to our
    # PumpMessages() loop.
    def OnDestroy(self, hwnd, msg, wparam, lparam):
        win32gui.PostQuitMessage(0) # Terminate the app.
        
    def _start_thread(self):
        import threading
        self.thread1 = threading.Thread(target=self._do_popen)
        self.thread1.start()
        
    def write(self, msg):
        setEditText(self.outtext, [msg], append=True)
        
    def DoRefresh(self):
        self.outbuf = ""
        setEditText(self.outtext, [''])
        self._start_thread()
        
    def _do_popen(self):        
        if not self.cmdline:
            return

        pop = subprocess.Popen(self.cmdline, 
                               shell=True,
                               stderr=subprocess.STDOUT,
                               stdout=subprocess.PIPE,
                               stdin=subprocess.PIPE)

        bytes = 0
        refresh_btn = win32gui.GetDlgItem(self.hwnd, IDC_BUTTON_REFRESH)
        win32gui.EnableWindow(refresh_btn, False)
        try:
            line = 0
            blocksize = 1024
            while pop.poll() == None:
                if line < 100:
                    out = pop.stdout.readline()
                    line += 1
                else:
                    out = pop.stdout.read(blocksize)
                    if blocksize < 1024 * 50:
                        blocksize *= 2
                bytes += len(out)
                self.write(out)
            out = pop.stdout.read()
            bytes += len(out)
            self.write(out)
        except IOError:
            pass

        win32gui.EnableWindow(refresh_btn, True)

def run(cmdline, title='Hg', modal=False):
    dlg = PopenDialog(cmdline=cmdline, title=title)
    if modal:
        dlg.DoModal()
    else:
        dlg.CreateWindow()
        win32gui.PumpMessages()
    
def get_option(args):
    long_opt_list =  ['command=', 'exepath=', 'listfile=', 'title=',
                      'root=', 'notify', 'deletelistfile']
    opts, args = getopt.getopt(args, "c:e:l:ndt:R:", long_opt_list)
    options = dict({'hgcmd': 'help', 'hgpath': 'hg'} )
    
    for o, a in opts:
        if o in ("-c", "--command"):
            options['hgcmd'] = a
        elif o in ("-l", "--listfile"):
            options['listfile'] = a
        elif o in ("-e", "--exepath"):
            options['hgpath'] = a
        elif o in ("-n", "--notify"):
            options['notify'] = True
        elif o in ("-t", "--title"):
            options['title'] = a
        elif o in ("-d", "--deletelistfile"):
            options['rmlistfile'] = True
        elif o in ("-R", "--root"):
            options['root'] = a

    return (options, args)

def get_list_from_file(filename):
    fd = open(filename, "r")
    lines = [ x.replace("\n", "") for x in fd.readlines() ]
    fd.close()
    return lines
    
if __name__=='__main__':
    if len(sys.argv) > 1:
        try:
            option, args = get_option(sys.argv[1:])
        except getopt.GetoptError, inst:
            print inst
            sys.exit(1)
        
        filelist = []
        if option.has_key('listfile'):
            filelist = get_list_from_file(option['listfile'])
            
        #cmdline = option['hgpath']
        cmdline = "hg %s" % option['hgcmd']
        if option.has_key('root'):
            cmdline += " --repository %s" % thgutil.shellquote(option['root'])
        if args:
            cmdline += " %s" % " ".join([(x) for x in args])
        if filelist:
            cmdline += " %s" % " ".join([thgutil.shellquote(x) for x in filelist])
                    
        opt = {}
        if option.has_key('title'):
            opt['title'] = option['title']
        elif option.has_key('root'):
            opt['title'] = "hg %s - %s" % (option['hgcmd'], option['root'])
        else:
            opt['title'] = "hg %s" % option['hgcmd']

        run(cmdline, **opt)
                             
        if option.has_key('notify'):
            for f in filelist:
                dir = os.path.isdir(f) and f or os.path.dirname(f)
                thgutil.shell_notify(os.path.abspath(dir))

        if option.has_key('rmlistfile'):
            os.unlink(option['listfile'])
            
    # ========== test cases ==========
    #run(['hg log -v', modal=True])
    #run(['hg', 'log', '-v'], modal=False)
    #run(['hg -R C:\hg\h1 log -v'])
    #run(['hg version'])
