'''
Binary document diff wrapper script

This script is converted into an executable by py2exe for use in
TortoiseHg binary packages.  It is then used by TortoiseHg as a visual
diff application for binary document types.

It takes two (diff) or four (merge) arguments, determines the file type
based on the file extension, then launches the appropriate document diff
script that THG has borrowed from the TortoiseSVN project.

This script is quite useless outside of a TortoiseHg binary install.
'''

import os
import sys
import subprocess
import shutil
import win32con
import win32api
import win32process
import locale

from mercurial import util

scripts = {
    'doc'  : ('diff-doc.js', 'merge-doc.js'),    # MS Word
    'docx' : ('diff-doc.js', 'merge-doc.js'),
    'docm' : ('diff-doc.js', 'merge-doc.js'),
    'ppt'  : ('diff-ppt.js',),                   # MS PowerPoint
    'pptx' : ('diff-ppt.js',),
    'pptm' : ('diff-ppt.js',),
    'xls'  : ('diff-xls.vbs',),                  # MS Excel
    'xlsx' : ('diff-xls.vbs',),
    'xlsm' : ('diff-xls.vbs',),
    'xlsb' : ('diff-xls.vbs',),
    'xlam' : ('diff-xls.vbs',),
    'ods'  : ('diff-odt.vbs', 'merge-ods.vbs'),  # OpenOffice Text
    'odt'  : ('diff-odt.vbs', 'merge-ods.vbs'),
    'sxw'  : ('diff-sxw.vbs', 'merge-ods.vbs'),  # OpenOffice Calc
    'nb'   : ('diff-nb.vbs',),                   # Mathematica Notebook
}

def safe_encode(string, encoding):
    if isinstance(string, unicode):
        return string.encode(encoding)

    return string

def main():
    args = sys.argv[1:]
    if len(args) not in (2, 4):
        print 'Two or four arguments expected:'
        print sys.argv[0], '[local] [other]'
        print sys.argv[0], '[local] [base] [other] [output]'
        sys.exit(1)
    elif len(args) == 2:
        local, other = [os.path.abspath(f) for f in args]
        base, ext = os.path.splitext(local)
    else:
        local, base, other, output = [os.path.abspath(f) for f in args]
        base, ext = os.path.splitext(output)

    if not ext or ext.lower()[1:] not in scripts.keys():
        print 'Unsupported file type', ext
        sys.exit(1)

    proc = win32api.GetCurrentProcess()
    try:
        # This will fail on windows < NT
        filename = win32process.GetModuleFileNameEx(proc, 0)
    except:
        filename = win32api.GetModuleFileName(0)
    path = os.path.join(os.path.dirname(filename), 'diff-scripts')
    if not os.path.isdir(path):
        print 'Diff scripts not found at', path
        sys.exit(1)

    use = scripts[ext.lower()[1:]]

    if 'xls' in use[0] and os.path.basename(local) == os.path.basename(other):
        # XLS hack; Excel will not diff two files if they have the same
        # basename.
        othertmp = other+'~x1'
        shutil.copy(other, othertmp)
        other = othertmp

    if len(args) == 2:
        script = os.path.join(path, use[0])
        cmd = ['wscript', script, other, local]
    elif len(use) == 1:
        print 'Unsupported file type for merge', local
        sys.exit(1)
    else:
        script = os.path.join(path, use[1])
        cmd = ['wscript', script, output, other, local, base]

    encoding = locale.getpreferredencoding(do_setlocale=True)
    cmd = [util.shellquote(safe_encode(arg, encoding)) for arg in cmd]
    cmdline = util.quotecommand(' '.join(cmd))
    proc = subprocess.Popen(cmdline, shell=True,
                            creationflags=win32con.CREATE_NO_WINDOW,
                            stderr=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stdin=subprocess.PIPE)
    return proc.communicate()

if __name__=='__main__':
    main()
