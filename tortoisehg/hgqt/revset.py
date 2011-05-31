# revset.py - revision set query dialog
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import revset, hg, error

from tortoisehg.hgqt import qtlib, cmdui
from tortoisehg.util import hglib
from tortoisehg.hgqt.i18n import _

from PyQt4.Qsci import QsciScintilla, QsciAPIs, QsciLexerPython
from PyQt4.QtCore import *
from PyQt4.QtGui import *

# TODO:
#  Connect to repoview revisionClicked events
#  Shift-Click rev range -> revision range X:Y
#  Ctrl-Click two revs -> DAG range X::Y
#  QFontMetrics.elidedText for help label

_common = (
    ('user(string)',
     _('Changesets where username contains string.')),
    ('keyword(string)',
     _('Search commit message, user name, and names of changed '
       'files for string.')),
    ('grep(regex)',
     _('Like "keyword(string)" but accepts a regex.')),
    ('outgoing([path])',
     _('Changesets not found in the specified destination repository, '
       'or the default push location.')),
    ('bookmark([name])',
       _('The named bookmark or all bookmarks.')),
    ('tag([name])',
       _('The named tag or all tags.')),
    ('tagged()',
     _('Changeset is tagged.')),
    ('head()',
     _('Changeset is a named branch head.')),
    ('merge()',
     _('Changeset is a merge changeset.')),
    ('closed()',
     _('Changeset is closed.')),
    ('date(interval)',
     _('Changesets within the interval, see <a href="http://www.selenic.com/'
       'mercurial/hg.1.html#dates">help dates</a>')),
    ('ancestor(single, single)',
     _('Greatest common ancestor of the two changesets.')),
)

_filepatterns = (
    ('file(pattern)',
     _('Changesets affecting files matched by pattern.  '
       'See <a href="http://www.selenic.com/mercurial/hg.1.html#patterns">'
       'help patterns</a>')),
    ('modifies(pattern)',
     _('Changesets which modify files matched by pattern.')),
    ('adds(pattern)',
     _('Changesets which add files matched by pattern.')),
    ('removes(pattern)',
     _('Changesets which remove files matched by pattern.')),
    ('contains(pattern)',
     _('Changesets containing files matched by pattern.')),
)

_ancestry = (
    ('branch(set)',
     _('All changesets belonging to the branches of changesets in set.')),
    ('heads(set)',
     _('Members of a set with no children in set.')),
    ('descendants(set)',
     _('Changesets which are descendants of changesets in set.')),
    ('ancestors(set)',
     _('Changesets that are ancestors of a changeset in set.')),
    ('children(set)',
     _('Child changesets of changesets in set.')),
    ('parents(set)',
     _('The set of all parents for all changesets in set.')),
    ('p1(set)',
     _('First parent for all changesets in set, or the working directory.')),
    ('p2(set)',
     _('Second parent for all changesets in set, or the working directory.')),
    ('roots(set)',
     _('Changesets whith no parent changeset in set.')),
    ('present(set)',
     _('An empty set, if any revision in set isn\'t found; otherwise, '
       'all revisions in set.')),
)

_logical = (
    ('min(set)',
     _('Changeset with lowest revision number in set.')),
    ('max(set)',
     _('Changeset with highest revision number in set.')),
    ('limit(set, n)',
     _('First n members of a set.')),
    ('sort(set[, [-]key...])',
     _('Sort set by keys.  The default sort order is ascending, specify a '
       'key as "-key" to sort in descending order.')),
    ('follow()',
     _('An alias for "::." (ancestors of the working copy\'s first parent).')),
    ('all()',
     _('All changesets, the same as 0:tip.')),
)

class RevisionSetQuery(QDialog):
    # Emit query string and resulting revision set
    queryIssued = pyqtSignal(QString, object)
    showMessage = pyqtSignal(QString)
    progress = pyqtSignal(QString, object, QString, QString, object)

    def __init__(self, repo, parent=None):
        QDialog.__init__(self, parent)

        self.repo = repo
        # Since the revset dialot belongs to a repository, we display
        # the repository name in the dialog title
        self.setWindowTitle(_('Revision Set Query') + ' - ' + repo.displayname)
        self.setWindowFlags(Qt.Window)

        layout = QVBoxLayout()
        layout.setMargin(0)
        layout.setContentsMargins(*(4,)*4)
        self.setLayout(layout)

        if 'hgsubversion' in repo.extensions():
            global _logical, _ancestry
            _logical = list(_logical) + [('fromsvn()',
                    _('all revisions converted from subversion')),]
            _ancestry = list(_ancestry) + [('svnrev(rev)',
                    _('changeset which represents converted svn revision')),]

        self.stbar = cmdui.ThgStatusBar(self)
        self.stbar.setSizeGripEnabled(False)
        self.stbar.lbl.setOpenExternalLinks(True)
        self.showMessage.connect(self.stbar.showMessage)
        self.progress.connect(self.stbar.progress)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(*(0,)*4)

        cgb = QGroupBox(_('Common sets'))
        cgb.setLayout(QVBoxLayout())
        cgb.layout().setContentsMargins(*(2,)*4)
        def setCommonHelp(item):
            self.stbar.showMessage(self.clw._help[self.clw.row(item)])
        self.clw = QListWidget(self)
        self.clw.addItems([x for x, y in _common])
        self.clw._help = [y for x, y in _common]
        self.clw.itemClicked.connect(setCommonHelp)
        cgb.layout().addWidget(self.clw)
        hbox.addWidget(cgb)

        fgb = QGroupBox(_('File pattern sets'))
        fgb.setLayout(QVBoxLayout())
        fgb.layout().setContentsMargins(*(2,)*4)
        def setFileHelp(item):
            self.stbar.showMessage(self.flw._help[self.flw.row(item)])
        self.flw = QListWidget(self)
        self.flw.addItems([x for x, y in _filepatterns])
        self.flw._help = [y for x, y in _filepatterns]
        self.flw.itemClicked.connect(setFileHelp)
        fgb.layout().addWidget(self.flw)
        hbox.addWidget(fgb)

        agb = QGroupBox(_('Set Ancestry'))
        agb.setLayout(QVBoxLayout())
        agb.layout().setContentsMargins(*(2,)*4)
        def setAncHelp(item):
            self.stbar.showMessage(self.alw._help[self.alw.row(item)])
        self.alw = QListWidget(self)
        self.alw.addItems([x for x, y in _ancestry])
        self.alw._help = [y for x, y in _ancestry]
        self.alw.itemClicked.connect(setAncHelp)
        agb.layout().addWidget(self.alw)
        hbox.addWidget(agb)

        lgb = QGroupBox(_('Set Logic'))
        lgb.setLayout(QVBoxLayout())
        lgb.layout().setContentsMargins(*(2,)*4)
        def setManipHelp(item):
            self.stbar.showMessage(self.llw._help[self.llw.row(item)])
        self.llw = QListWidget(self)
        self.llw.addItems([x for x, y in _logical])
        self.llw._help = [y for x, y in _logical]
        self.llw.itemClicked.connect(setManipHelp)
        lgb.layout().addWidget(self.llw)
        hbox.addWidget(lgb)

        # Clicking on one listwidget should clear selection of the others
        listwidgets = (self.clw, self.flw, self.alw, self.llw)
        for w in listwidgets:
            w.itemClicked.connect(self.itemClicked)
            #w.itemActivated.connect(self.returnPressed)
            for w2 in listwidgets:
                if w is not w2:
                    w.itemClicked.connect(w2.clearSelection)

        layout.addLayout(hbox, 1)

        self.entry = RevsetEntry(self)
        self.entry.addCompletions(_logical, _ancestry, _filepatterns, _common)
        layout.addWidget(self.entry, 0)

        txt = _('<a href="http://www.selenic.com/mercurial/hg.1.html#revsets">'
                'help revsets</a>')
        helpLabel = QLabel(txt)
        helpLabel.setOpenExternalLinks(True)
        self.stbar.addPermanentWidget(helpLabel)
        layout.addWidget(self.stbar, 0)
        QShortcut(QKeySequence('Return'), self, self.returnPressed)
        QShortcut(QKeySequence('Escape'), self, self.reject)

    def runQuery(self):
        self.entry.setEnabled(False)
        self.showMessage.emit(_('Searching...'))
        self.progress.emit(*cmdui.startProgress(_('Running'), _('query')))

        self.refreshing = RevsetThread(self.repo, self.entry.text(), self)
        self.refreshing.showMessage.connect(self.showMessage)
        self.refreshing.queryIssued.connect(self.queryIssued)
        self.refreshing.finished.connect(self.queryFinished)
        self.refreshing.setCursorPosition.connect(self.entry.setCursorPosition)
        self.refreshing.start()

    def queryFinished(self):
        self.refreshing.wait()
        self.entry.setEnabled(True)
        self.progress.emit(*cmdui.stopProgress(_('Running')))

    def returnPressed(self):
        text = self.entry.text()
        if self.entry.hasSelectedText():
            lineFrom, indexFrom, lineTo, indexTo = self.entry.getSelection()
            start = self.entry.positionFromLineIndex(lineFrom, indexFrom)
            end = self.entry.positionFromLineIndex(lineTo, indexTo)
            sel = self.entry.selectedText()
            if sel.count('(') and sel.contains(')'):
                bopen = sel.indexOf('(')
                bclose = sel.lastIndexOf(')')
                if bopen < bclose:
                    self.entry.setSelection(lineFrom, start+bopen+1,
                                            lineFrom, start+bclose)
                    self.entry.setFocus()
                    return
            self.entry.setSelection(lineTo, indexTo,
                                    lineTo, indexTo)
        else:
            self.runQuery()
        self.entry.setFocus()


    def itemClicked(self, item):
        self.entry.beginUndoAction()
        text = self.entry.text()
        itext, ilen = item.text(), len(item.text())
        if self.entry.hasSelectedText():
            # replace selection
            lineFrom, indexFrom, lineTo, indexTo = self.entry.getSelection()
            start = self.entry.positionFromLineIndex(lineFrom, indexFrom)
            end = self.entry.positionFromLineIndex(lineTo, indexTo)
            newtext = text[:start] + itext + text[end:]
            self.entry.setText(newtext)
            self.entry.setSelection(lineFrom, indexFrom,
                                    lineFrom, indexFrom+ilen)
        else:
            line, index = self.entry.getCursorPosition()
            pos = self.entry.positionFromLineIndex(line, index)
            if len(text) <= pos:
                # cursor at end of text, append
                if text and text[-1] != u' ':
                    text = text + u' '
                newtext = text + itext
                self.entry.setText(newtext)
                self.entry.setSelection(line, len(text), line, len(newtext))
            elif text[pos] == u' ':
                # cursor is at a space, insert item
                newtext = text[:pos] + itext + text[pos:]
                self.entry.setText(newtext)
                self.entry.setSelection(line, pos, line, pos+ilen)
            else:
                # cursor is on text, wrap current word
                start, end = pos, pos
                while start and text[start-1] != u' ':
                    start = start-1
                while end < len(text) and text[end] != u' ':
                    end = end+1
                bopen = itext.indexOf('(')
                newtext = text[:start] + itext[:bopen+1] + text[start:end] + \
                          ')' + text[end:]
                self.entry.setText(newtext)
                self.entry.setSelection(line, start, line, end+bopen+2)
        self.entry.endUndoAction()

    def accept(self):
        self.hide()

    def reject(self):
        self.accept()

class RevsetEntry(QsciScintilla):
    def __init__(self, parent=None):
        super(RevsetEntry, self).__init__(parent)
        self.setMarginWidth(1, 0)
        self.setReadOnly(False)
        self.setUtf8(True)
        self.setCaretWidth(10)
        self.setCaretLineBackgroundColor(QColor("#e6fff0"))
        self.setCaretLineVisible(True)
        self.setAutoIndent(True)
        self.setMatchedBraceBackgroundColor(Qt.yellow)
        self.setIndentationsUseTabs(False)
        self.setBraceMatching(QsciScintilla.SloppyBraceMatch)

        self.setWrapMode(QsciScintilla.WrapWord)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        sp = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        sp.setHorizontalStretch(1)
        sp.setVerticalStretch(0)
        self.setSizePolicy(sp)

        self.setAutoCompletionThreshold(2)
        self.setAutoCompletionSource(QsciScintilla.AcsAPIs)
        self.setAutoCompletionFillupsEnabled(True)
        self.setLexer(QsciLexerPython(self))
        self.lexer().setFont(qtlib.getfont('fontcomment').font())
        self.apis = QsciAPIs(self.lexer())

    def addCompletions(self, *lists):
        for list in lists:
            for x, y in list:
                self.apis.add(x)
        self.apis.prepare()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            event.ignore()
            return
        if event.key() in (Qt.Key_Enter, Qt.Key_Return):
            if not self.isListActive():
                event.ignore()
                return
        super(RevsetEntry, self).keyPressEvent(event)

    def sizeHint(self):
        return QSize(10, self.fontMetrics().height())



class RevsetThread(QThread):
    queryIssued = pyqtSignal(QString, object)
    showMessage = pyqtSignal(QString)
    setCursorPosition = pyqtSignal(int, int)

    def __init__(self, repo, query, parent):
        super(RevsetThread, self).__init__(parent)
        self.repo = hg.repository(repo.ui, repo.root)
        self.text = hglib.fromunicode(query)
        self.query = query

    def run(self):
        if '(' not in self.text:
            try:
                ctx = self.repo[self.text]
                self.showMessage.emit(_('found revision'))
                self.queryIssued.emit(self.query, [ctx.rev()])
                return
            except (error.RepoError, error.LookupError, error.Abort):
                self.text = 'keyword("%s")' % self.text
        cwd = os.getcwd()
        try:
            os.chdir(self.repo.root)
            func = hglib.revsetmatch(self.repo.ui, self.text)
            l = []
            for c in func(self.repo, range(len(self.repo))):
                l.append(c)
            if len(l):
                self.showMessage.emit(_('%d matches found') % len(l))
            else:
                self.showMessage.emit(_('No matches found'))
            self.queryIssued.emit(self.query, l)
        except error.ParseError, e:
            if len(e.args) == 2:
                msg, pos = e.args
                self.setCursorPosition.emit(0, pos)
            else:
                msg = e.args[0]
            self.showMessage.emit(_('Parse Error: ') + hglib.tounicode(msg))
        except TypeError:
            raise
        except Exception, e:
            self.showMessage.emit(_('Invalid query: ')+hglib.tounicode(str(e)))

        os.chdir(cwd)

def run(ui, *pats, **opts):
    from tortoisehg.util import paths
    from tortoisehg.hgqt import thgrepo
    repo = thgrepo.repository(ui, path=paths.find_root())
    return RevisionSetQuery(repo)
