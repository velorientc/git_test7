# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'C:\Users\adi\hgrepos\thg-qt\tortoisehg\hgqt\workbench.ui'
#
# Created: Wed May 12 00:19:14 2010
#      by: PyQt4 UI code generator 4.7.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(671, 669)
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icons/log.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        MainWindow.setWindowIcon(icon)
        self.centralwidget = QtGui.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.horizontalLayout = QtGui.QHBoxLayout(self.centralwidget)
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setMargin(0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.repoTabsWidget = QtGui.QTabWidget(self.centralwidget)
        self.repoTabsWidget.setDocumentMode(True)
        self.repoTabsWidget.setTabsClosable(True)
        self.repoTabsWidget.setMovable(True)
        self.repoTabsWidget.setObjectName("repoTabsWidget")
        self.firstRepoTab = QtGui.QWidget()
        self.firstRepoTab.setObjectName("firstRepoTab")
        self.repoTabsWidget.addTab(self.firstRepoTab, "")
        self.horizontalLayout.addWidget(self.repoTabsWidget)
        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QtGui.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 671, 19))
        self.menubar.setObjectName("menubar")
        self.menuFile = QtGui.QMenu(self.menubar)
        self.menuFile.setObjectName("menuFile")
        self.menuHelp = QtGui.QMenu(self.menubar)
        self.menuHelp.setObjectName("menuHelp")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QtGui.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)
        self.toolBar_file = QtGui.QToolBar(MainWindow)
        self.toolBar_file.setObjectName("toolBar_file")
        MainWindow.addToolBar(QtCore.Qt.ToolBarArea(QtCore.Qt.TopToolBarArea), self.toolBar_file)
        self.toolBar_edit = QtGui.QToolBar(MainWindow)
        self.toolBar_edit.setEnabled(True)
        self.toolBar_edit.setObjectName("toolBar_edit")
        MainWindow.addToolBar(QtCore.Qt.ToolBarArea(QtCore.Qt.TopToolBarArea), self.toolBar_edit)
        self.toolBar_treefilters = QtGui.QToolBar(MainWindow)
        self.toolBar_treefilters.setEnabled(True)
        self.toolBar_treefilters.setObjectName("toolBar_treefilters")
        MainWindow.addToolBar(QtCore.Qt.ToolBarArea(QtCore.Qt.TopToolBarArea), self.toolBar_treefilters)
        self.toolBar_diff = QtGui.QToolBar(MainWindow)
        self.toolBar_diff.setObjectName("toolBar_diff")
        MainWindow.addToolBar(QtCore.Qt.ToolBarArea(QtCore.Qt.TopToolBarArea), self.toolBar_diff)
        self.toolBar_help = QtGui.QToolBar(MainWindow)
        self.toolBar_help.setObjectName("toolBar_help")
        MainWindow.addToolBar(QtCore.Qt.ToolBarArea(QtCore.Qt.TopToolBarArea), self.toolBar_help)
        self.actionOpen_repository = QtGui.QAction(MainWindow)
        self.actionOpen_repository.setObjectName("actionOpen_repository")
        self.actionRefresh = QtGui.QAction(MainWindow)
        self.actionRefresh.setObjectName("actionRefresh")
        self.actionQuit = QtGui.QAction(MainWindow)
        self.actionQuit.setShortcut("None")
        self.actionQuit.setObjectName("actionQuit")
        self.actionAbout = QtGui.QAction(MainWindow)
        self.actionAbout.setObjectName("actionAbout")
        self.actionDisplayAllBranches = QtGui.QAction(MainWindow)
        self.actionDisplayAllBranches.setObjectName("actionDisplayAllBranches")
        self.actionHelp = QtGui.QAction(MainWindow)
        self.actionHelp.setObjectName("actionHelp")
        self.menuFile.addAction(self.actionOpen_repository)
        self.menuFile.addAction(self.actionRefresh)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.actionQuit)
        self.menuHelp.addAction(self.actionAbout)
        self.menuHelp.addAction(self.actionHelp)
        self.menubar.addAction(self.menuFile.menuAction())
        self.menubar.addAction(self.menuHelp.menuAction())
        self.toolBar_file.addAction(self.actionRefresh)
        self.toolBar_help.addAction(self.actionHelp)

        self.retranslateUi(MainWindow)
        self.repoTabsWidget.setCurrentIndex(0)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QtGui.QApplication.translate("MainWindow", "MainWindow", None, QtGui.QApplication.UnicodeUTF8))
        self.repoTabsWidget.setTabText(self.repoTabsWidget.indexOf(self.firstRepoTab), QtGui.QApplication.translate("MainWindow", "repo1", None, QtGui.QApplication.UnicodeUTF8))
        self.menuFile.setTitle(QtGui.QApplication.translate("MainWindow", "&File", None, QtGui.QApplication.UnicodeUTF8))
        self.menuHelp.setTitle(QtGui.QApplication.translate("MainWindow", "&Help", None, QtGui.QApplication.UnicodeUTF8))
        self.toolBar_file.setWindowTitle(QtGui.QApplication.translate("MainWindow", "File toolbar", None, QtGui.QApplication.UnicodeUTF8))
        self.toolBar_edit.setWindowTitle(QtGui.QApplication.translate("MainWindow", "Edit toolbar", None, QtGui.QApplication.UnicodeUTF8))
        self.toolBar_treefilters.setWindowTitle(QtGui.QApplication.translate("MainWindow", "Filter toolbar", None, QtGui.QApplication.UnicodeUTF8))
        self.toolBar_diff.setWindowTitle(QtGui.QApplication.translate("MainWindow", "Diff toolbar", None, QtGui.QApplication.UnicodeUTF8))
        self.toolBar_help.setWindowTitle(QtGui.QApplication.translate("MainWindow", "Help toolbar", None, QtGui.QApplication.UnicodeUTF8))
        self.actionOpen_repository.setText(QtGui.QApplication.translate("MainWindow", "&Open repository", None, QtGui.QApplication.UnicodeUTF8))
        self.actionOpen_repository.setShortcut(QtGui.QApplication.translate("MainWindow", "Ctrl+O", None, QtGui.QApplication.UnicodeUTF8))
        self.actionRefresh.setText(QtGui.QApplication.translate("MainWindow", "&Refresh", None, QtGui.QApplication.UnicodeUTF8))
        self.actionRefresh.setShortcut(QtGui.QApplication.translate("MainWindow", "Ctrl+R", None, QtGui.QApplication.UnicodeUTF8))
        self.actionQuit.setText(QtGui.QApplication.translate("MainWindow", "E&xit", None, QtGui.QApplication.UnicodeUTF8))
        self.actionQuit.setIconText(QtGui.QApplication.translate("MainWindow", "Exit", None, QtGui.QApplication.UnicodeUTF8))
        self.actionQuit.setToolTip(QtGui.QApplication.translate("MainWindow", "Exit", None, QtGui.QApplication.UnicodeUTF8))
        self.actionAbout.setText(QtGui.QApplication.translate("MainWindow", "About", None, QtGui.QApplication.UnicodeUTF8))
        self.actionDisplayAllBranches.setText(QtGui.QApplication.translate("MainWindow", "displayAllBranches", None, QtGui.QApplication.UnicodeUTF8))
        self.actionHelp.setText(QtGui.QApplication.translate("MainWindow", "Help", None, QtGui.QApplication.UnicodeUTF8))

import workbench_rc
