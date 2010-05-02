# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'C:\Users\adi\hgrepos\thg-qt\tortoisehg\hgqt\FileDiffDialog.ui'
#
# Created: Sun May 02 12:47:23 2010
#      by: PyQt4 UI code generator 4.7.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(620, 546)
        self.centralwidget = QtGui.QWidget(MainWindow)
        self.centralwidget.setGeometry(QtCore.QRect(0, 33, 620, 513))
        self.centralwidget.setObjectName("centralwidget")
        self.verticalLayout = QtGui.QVBoxLayout(self.centralwidget)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.splitter = QtGui.QSplitter(self.centralwidget)
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter.setObjectName("splitter")
        self.layoutWidget = QtGui.QWidget(self.splitter)
        self.layoutWidget.setObjectName("layoutWidget")
        self.horizontalLayout = QtGui.QHBoxLayout(self.layoutWidget)
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.tableView_revisions_left = HgRepoView(self.layoutWidget)
        self.tableView_revisions_left.setAlternatingRowColors(True)
        self.tableView_revisions_left.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.tableView_revisions_left.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.tableView_revisions_left.setShowGrid(False)
        self.tableView_revisions_left.setObjectName("tableView_revisions_left")
        self.horizontalLayout.addWidget(self.tableView_revisions_left)
        self.tableView_revisions_right = HgRepoView(self.layoutWidget)
        self.tableView_revisions_right.setAlternatingRowColors(True)
        self.tableView_revisions_right.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.tableView_revisions_right.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.tableView_revisions_right.setShowGrid(False)
        self.tableView_revisions_right.setObjectName("tableView_revisions_right")
        self.horizontalLayout.addWidget(self.tableView_revisions_right)
        self.layoutWidget1 = QtGui.QWidget(self.splitter)
        self.layoutWidget1.setObjectName("layoutWidget1")
        self.horizontalLayout_2 = QtGui.QHBoxLayout(self.layoutWidget1)
        self.horizontalLayout_2.setSpacing(0)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.frame = QtGui.QFrame(self.layoutWidget1)
        self.frame.setFrameShape(QtGui.QFrame.NoFrame)
        self.frame.setFrameShadow(QtGui.QFrame.Raised)
        self.frame.setObjectName("frame")
        self.horizontalLayout_2.addWidget(self.frame)
        self.verticalLayout.addWidget(self.splitter)
        MainWindow.setCentralWidget(self.centralwidget)
        self.toolBar = QtGui.QToolBar(MainWindow)
        self.toolBar.setGeometry(QtCore.QRect(0, 0, 121, 33))
        self.toolBar.setObjectName("toolBar")
        MainWindow.addToolBar(QtCore.Qt.ToolBarArea(QtCore.Qt.TopToolBarArea), self.toolBar)
        MainWindow.insertToolBarBreak(self.toolBar)
        self.toolBar_edit = QtGui.QToolBar(MainWindow)
        self.toolBar_edit.setGeometry(QtCore.QRect(121, 0, 499, 33))
        self.toolBar_edit.setObjectName("toolBar_edit")
        MainWindow.addToolBar(QtCore.Qt.ToolBarArea(QtCore.Qt.TopToolBarArea), self.toolBar_edit)
        self.actionClose = QtGui.QAction(MainWindow)
        self.actionClose.setObjectName("actionClose")
        self.actionReload = QtGui.QAction(MainWindow)
        self.actionReload.setObjectName("actionReload")
        self.toolBar.addAction(self.actionClose)
        self.toolBar.addAction(self.actionReload)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)
        MainWindow.setTabOrder(self.tableView_revisions_left, self.tableView_revisions_right)

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QtGui.QApplication.translate("MainWindow", "MainWindow", None, QtGui.QApplication.UnicodeUTF8))
        self.toolBar.setWindowTitle(QtGui.QApplication.translate("MainWindow", "toolBar", None, QtGui.QApplication.UnicodeUTF8))
        self.toolBar_edit.setWindowTitle(QtGui.QApplication.translate("MainWindow", "toolBar_2", None, QtGui.QApplication.UnicodeUTF8))
        self.actionClose.setText(QtGui.QApplication.translate("MainWindow", "Close", None, QtGui.QApplication.UnicodeUTF8))
        self.actionClose.setShortcut(QtGui.QApplication.translate("MainWindow", "Ctrl+Q", None, QtGui.QApplication.UnicodeUTF8))
        self.actionReload.setText(QtGui.QApplication.translate("MainWindow", "Reload", None, QtGui.QApplication.UnicodeUTF8))
        self.actionReload.setShortcut(QtGui.QApplication.translate("MainWindow", "Ctrl+R", None, QtGui.QApplication.UnicodeUTF8))

from repoview import HgRepoView
