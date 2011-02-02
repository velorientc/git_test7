#!/usr/bin/env python
# plot-annotate-colors.py - Display how annotation colors are assigned
#
# Copyright 2010 Yuya Nishihara <yuya@tcha.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.
import os, sys, math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from mercurial import hg, ui, cmdutil, util
from tortoisehg.util import colormap, hglib

from PyQt4.QtCore import *
from PyQt4.QtGui import *

SECS_PER_DAY = 24 * 60 * 60

class ColorPlot(QWidget):
    """Display annotation colors as x-y graph

    ::
        +-------------------------------------------------> age
        |
        |   o  ... filled by its color
        |
        |           O  ... size of circle describes number of lines
        |
        |                                        *
        |                                        ... missing ctx is
        |                                            filled by yellow
        |                                            (error marker)
        v
        committer
    """

    def __init__(self, parent=None):
        super(ColorPlot, self).__init__(parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding,
                                       QSizePolicy.Expanding))
        pal = QPalette()
        pal.setColor(self.backgroundRole(), QColor('black'))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        self._updatetimer = QTimer(self, singleShot=True)
        self._updatetimer.timeout.connect(self.update)

        self._maxhues = None
        self._maxsaturations = None
        self._mindate = None
        self._maxcolors = 0

        self._latestdate = None
        self._fctxs = None

    def paintEvent(self, event):
        if self._fctxs is None:
            return

        mindate = None
        if self._mindate:
            mindate = self._latestdate - self._mindate * SECS_PER_DAY
        palette, cm = colormap._makeannotatepalette(
            list(sorted(set(self._fctxs), key=lambda fctx: -fctx.date()[0])),
            now=self._latestdate, maxcolors=self._maxcolors,
            maxhues=self._maxhues, maxsaturations=self._maxsaturations,
            mindate=mindate)

        weights = {}
        for fctx in self._fctxs:
            try:
                weights[fctx] += 1
            except KeyError:
                weights[fctx] = 1

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for fctx, w in weights.iteritems():
            i = abs(hash(fctx.user()))
            j = self._latestdate - fctx.date()[0]
            c = cm.get_color(fctx, self._latestdate)
            if c not in palette:
                b = QBrush(QColor('yellow'), Qt.Dense4Pattern)  # error marker
            else:
                b = QBrush(QColor(c))
            p.setPen(QPen(b, math.sqrt(w) * 2, Qt.SolidLine, Qt.RoundCap))
            p.drawPoint(j / SECS_PER_DAY + 2,
                        i / (sys.maxint / (self.height() - 4)) + 2)

        p.setPen(QColor('yellow'))
        p.setFont(QFont('monospace', 8))
        p.drawText(2, self.height() - 8,
                   'maxsaturations: %d' % cm._maxsaturations)

    def sizeHint(self):
        return QSize(365, 200)

    @pyqtSlot(int)
    def setMaxHues(self, value):
        self._maxhues = value or None
        self._updatetimer.start(100)

    @pyqtSlot(int)
    def setMaxSaturations(self, value):
        self._maxsaturations = value or None
        self._updatetimer.start(100)

    @pyqtSlot(int)
    def setMinDate(self, value):
        self._mindate = value or None
        self._updatetimer.start(100)

    @pyqtSlot(int)
    def setMaxColors(self, value):
        self._maxcolors = value
        self._updatetimer.start(100)

    def plot(self, repo, canonpath, rev='.'):
        latestfctx = repo[rev][canonpath]
        self._fctxs = [fctx for fctx, line in latestfctx.annotate(follow=True)]
        self._latestdate = latestfctx.date()[0]
        self._updatetimer.start(100)

class ColorPlotter(QWidget):
    def __init__(self, parent=None):
        super(ColorPlotter, self).__init__(parent)
        self.setLayout(QVBoxLayout(self))
        self._plot = ColorPlot(self)
        self.layout().addWidget(self._plot)

        form = QFormLayout()
        self.layout().addLayout(form)

        self._maxhues_edit = QSpinBox(self, minimum=0, maximum=360,
                                      specialValueText='inf')
        self._maxhues_edit.valueChanged.connect(self._plot.setMaxHues)
        self._maxhues_edit.setValue(8)
        form.addRow('Max Hues (committers):', self._maxhues_edit)

        self._maxsats_edit = QSpinBox(self, minimum=0, maximum=255,
                                      specialValueText='inf')
        self._maxsats_edit.valueChanged.connect(self._plot.setMaxSaturations)
        self._maxsats_edit.setValue(16)
        form.addRow('Max Saturations (ages):', self._maxsats_edit)

        self._mindate_edit = QSpinBox(self, minimum=0, maximum=720,
                                      specialValueText='n/a')
        self._mindate_edit.valueChanged.connect(self._plot.setMinDate)
        self._mindate_edit.setValue(365)
        form.addRow('Minimal revision age to include', self._mindate_edit)

        self._maxcols_edit = QSpinBox(self, minimum=0, maximum=255)
        self._maxcols_edit.valueChanged.connect(self._plot.setMaxColors)
        self._maxcols_edit.setValue(32)
        form.addRow('Max Colors (palette size):', self._maxcols_edit)

    @pyqtSlot(unicode)
    def setPath(self, path):
        spath = hglib.fromunicode(path)
        reporoot = cmdutil.findrepo(os.path.abspath(spath))
        if not reporoot:
            QMessageBox.warning(self, 'Repository Not Found',
                                'Repository not found for path: %s' % path)
        repo = hg.repository(ui.ui(), reporoot)
        canonpath = util.canonpath(repo.root, os.getcwd(), spath)
        self._plot.plot(repo, canonpath)

class ColorPlotterWindow(QMainWindow):
    def __init__(self, parent=None):
        super(ColorPlotterWindow, self).__init__(parent)
        self._plotter = ColorPlotter(self)
        self.setCentralWidget(self._plotter)

        self.setMenuBar(QMenuBar())
        filemenu = self.menuBar().addMenu('&File')
        filemenu.addAction('&Open', self._openFile, QKeySequence.Open)

    @pyqtSlot()
    def _openFile(self):
        path = QFileDialog.getOpenFileName(self, 'File to Annotate')
        if path:
            self.setPath(path)

    @pyqtSlot(unicode)
    def setPath(self, path):
        self.setWindowFilePath(path)
        self._plotter.setPath(path)

def main(args=sys.argv):
    app = QApplication(args)
    w = ColorPlotterWindow()
    w.show()
    if len(args) > 1:
        QTimer.singleShot(100, lambda: w.setPath(args[1]))
    return app.exec_()

if __name__ == '__main__':
    sys.exit(main())
