# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'C:\Users\adi\hgrepos\thg-qt\tortoisehg\hgqt\fileviewer.ui'
#
# Created: Sun May 02 11:32:38 2010
#      by: PyQt4 UI code generator 4.7.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(481, 438)
        self.centralwidget = QtGui.QWidget(MainWindow)
        self.centralwidget.setGeometry(QtCore.QRect(0, 33, 481, 405))
        self.centralwidget.setObjectName("centralwidget")
        self.verticalLayout = QtGui.QVBoxLayout(self.centralwidget)
        self.verticalLayout.setMargin(2)
        self.verticalLayout.setObjectName("verticalLayout")
        self.splitter = QtGui.QSplitter(self.centralwidget)
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter.setObjectName("splitter")
        self.tableView_revisions = HgRepoView(self.splitter)
        self.tableView_revisions.setAlternatingRowColors(True)
        self.tableView_revisions.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.tableView_revisions.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.tableView_revisions.setShowGrid(False)
        self.tableView_revisions.setGridStyle(QtCore.Qt.NoPen)
        self.tableView_revisions.setObjectName("tableView_revisions")
        self.textView = HgFileView(self.splitter)
        self.textView.setObjectName("textView")
        self.verticalLayout.addWidget(self.splitter)
        MainWindow.setCentralWidget(self.centralwidget)
        self.toolBar_edit = QtGui.QToolBar(MainWindow)
        self.toolBar_edit.setGeometry(QtCore.QRect(0, 0, 481, 33))
        self.toolBar_edit.setObjectName("toolBar_edit")
        MainWindow.addToolBar(QtCore.Qt.ToolBarArea(QtCore.Qt.TopToolBarArea), self.toolBar_edit)
        self.actionClose = QtGui.QAction(MainWindow)
        self.actionClose.setObjectName("actionClose")
        self.actionReload = QtGui.QAction(MainWindow)
        self.actionReload.setObjectName("actionReload")
        self.toolBar_edit.addAction(self.actionClose)
        self.toolBar_edit.addAction(self.actionReload)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QtGui.QApplication.translate("MainWindow", "hg FileViewer", None, QtGui.QApplication.UnicodeUTF8))
        self.toolBar_edit.setWindowTitle(QtGui.QApplication.translate("MainWindow", "toolBar", None, QtGui.QApplication.UnicodeUTF8))
        self.actionClose.setText(QtGui.QApplication.translate("MainWindow", "Close", None, QtGui.QApplication.UnicodeUTF8))
        self.actionClose.setShortcut(QtGui.QApplication.translate("MainWindow", "Ctrl+Q", None, QtGui.QApplication.UnicodeUTF8))
        self.actionReload.setText(QtGui.QApplication.translate("MainWindow", "Reload", None, QtGui.QApplication.UnicodeUTF8))
        self.actionReload.setShortcut(QtGui.QApplication.translate("MainWindow", "Ctrl+R", None, QtGui.QApplication.UnicodeUTF8))

from hgfileview import HgFileView
from repoview import HgRepoView
