# chunks.py - TortoiseHg patch/diff browser and editor
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt import qtlib, thgrepo, qscilib, lexers
from tortoisehg.hgqt import filelistmodel, filelistview, fileview

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import Qsci

qsci = Qsci.QsciScintilla

class ChunksWidget(QWidget):

    linkActivated = pyqtSignal(QString)
    showMessage = pyqtSignal(QString)

    def __init__(self, repo, ctx):
        QWidget.__init__(self)

        self.repo = repo

        SP = QSizePolicy
        sp = SP(SP.Preferred, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.sizePolicy().hasHeightForWidth())
        self.setSizePolicy(sp)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setMargin(0)
        layout.setContentsMargins(2, 2, 2, 2)
        self.setLayout(layout)

        self.splitter = QSplitter(self)
        self.layout().addWidget(self.splitter)

        sp = SP(SP.Expanding, SP.Expanding)
        sp.setHorizontalStretch(0)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.splitter.sizePolicy().hasHeightForWidth())
        self.splitter.setSizePolicy(sp)
        self.splitter.setOrientation(Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)

        self.filelist = filelistview.HgFileListView(self)

        self.fileListFrame = QFrame(self.splitter)
        sp = SP(SP.Preferred, SP.Preferred)
        sp.setHorizontalStretch(3)
        sp.setVerticalStretch(0)
        sp.setHeightForWidth(self.fileListFrame.sizePolicy().hasHeightForWidth())
        self.fileListFrame.setSizePolicy(sp)
        self.fileListFrame.setFrameShape(QFrame.NoFrame)
        vbox = QVBoxLayout()
        vbox.setSpacing(0)
        vbox.setMargin(0)
        vbox.addWidget(self.filelist)
        self.fileListFrame.setLayout(vbox)

        self.diffbrowse = DiffBrowser(self.splitter)
        self.diffbrowse.setFont(qtlib.getfont('fontlog').font())
        self.diffbrowse.showMessage.connect(self.showMessage)
        self.diffbrowse.linkActivated.connect(self.linkActivated)
        self.setContext(ctx or repo.changectx(None))

    @pyqtSlot(object, object, object)
    def displayFile(self, file, rev, status):
        self.diffbrowse.displayFile(file, status)

    def setContext(self, ctx):
        self.filelistmodel = filelistmodel.HgFileListModel(self.repo, self)
        self.filelist.setModel(self.filelistmodel)
        self.filelist.fileRevSelected.connect(self.displayFile)
        self.filelist.clearDisplay.connect(self.diffbrowse.clearDisplay)
        self.diffbrowse.setContext(ctx)
        self.filelistmodel.setContext(ctx)

    def refresh(self):
        f = self.filelist.currentFile()
        ctx = self.filelistmodel._ctx
        if isintance(ctx, thgrepo.patchctx):
            # if patch mtime has not changed, it could return the same ctx
            ctx = self.repo.changectx(ctx.path)
        else:
            self.repo.thginvalidate()
            ctx = self.repo.changectx(ctx.node())
        self.filelistmodel.setContext(ctx)
        if f in ctx:
            self.filelist.selectFile(f)

class DiffBrowser(QFrame):
    """diff browser"""

    linkActivated = pyqtSignal(QString)
    showMessage = pyqtSignal(QString)

    def __init__(self, parent):
        QFrame.__init__(self, parent)
        self._ctx = None
        framelayout = QVBoxLayout(self)
        framelayout.setContentsMargins(0,0,0,0)
        framelayout.setSpacing(0)

        self.filenamelabel = w = QLabel()
        w.setWordWrap(True)
        f = w.textInteractionFlags()
        w.setTextInteractionFlags(f | Qt.TextSelectableByMouse)
        w.linkActivated.connect(self.linkActivated)
        self.layout().addWidget(w)

        self.extralabel = w = QLabel()
        w.setWordWrap(True)
        w.linkActivated.connect(self.linkActivated)
        self.layout().addWidget(w)
        w.hide()

        self.sci = qscilib.Scintilla(self)
        self.sci.setFrameStyle(0)
        self.sci.setReadOnly(True)
        self.sci.setUtf8(True)
        self.sci.setWrapMode(qsci.WrapCharacter)
        self.sci.installEventFilter(qscilib.KeyPressInterceptor(self))
        self.sci.setCaretLineVisible(False)
        self.sci.setMarginLineNumbers(1, False)
        self.sci.setMarginWidth(1, '')
        self.layout().addWidget(self.sci, 1)

    def setContext(self, ctx):
        self._ctx = ctx
        self.sci.setTabWidth(ctx._repo.tabwidth)
        if ctx._repo.wsvisible == 'Visible':
            self.sci.setWhitespaceVisibility(qsci.WsVisible)
        elif ctx._repo.wsvisible == 'VisibleAfterIndent':
            self.sci.setWhitespaceVisibility(qsci.WsVisibleAfterIndent)
        else:
            self.sci.setWhitespaceVisibility(qsci.WsInvisible)

    def clearDisplay(self):
        self.sci.clear()
        self.filenamelabel.setText(' ')
        self.extralabel.hide()

    def displayFile(self, filename, status):
        self.clearDisplay()

        fd = fileview.FileData(self._ctx, None, filename, status)

        if fd.elabel:
            self.extralabel.setText(fd.elabel)
            self.extralabel.show()
        else:
            self.extralabel.hide()
        self.filenamelabel.setText(fd.flabel)

        if not fd.isValid() or not fd.diff:
            self.sci.setText(fd.error or '')
        else:
            lexer = lexers.get_diff_lexer(self)
            self.sci.setLexer(lexer)
            # TODO: do patch chunking here using record.parsepatch()
            # TODO: use indicators to represent current and selection state
            self.sci.setText(fd.diff)

def run(ui, *pats, **opts):
    'for testing purposes only'
    from tortoisehg.util import paths
    repo = thgrepo.repository(ui, path=paths.find_root())
    return ChunksWidget(repo, None)
