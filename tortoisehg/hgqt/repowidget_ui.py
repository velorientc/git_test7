# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'C:\Users\adi\hgrepos\thg-qt\tortoisehg\hgqt\repowidget.ui'
#
# Created: Sat May 15 11:32:44 2010
#      by: PyQt4 UI code generator 4.7.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(510, 506)
        self.horizontalLayout = QtGui.QHBoxLayout(Form)
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setMargin(0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.revisions_splitter = QtGui.QSplitter(Form)
        self.revisions_splitter.setOrientation(QtCore.Qt.Vertical)
        self.revisions_splitter.setObjectName("revisions_splitter")
        self.repoview = HgRepoView(self.revisions_splitter)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.repoview.sizePolicy().hasHeightForWidth())
        self.repoview.setSizePolicy(sizePolicy)
        self.repoview.setFrameShape(QtGui.QFrame.StyledPanel)
        self.repoview.setObjectName("repoview")
        self.frame_maincontent = QtGui.QFrame(self.revisions_splitter)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame_maincontent.sizePolicy().hasHeightForWidth())
        self.frame_maincontent.setSizePolicy(sizePolicy)
        self.frame_maincontent.setFrameShape(QtGui.QFrame.NoFrame)
        self.frame_maincontent.setFrameShadow(QtGui.QFrame.Plain)
        self.frame_maincontent.setObjectName("frame_maincontent")
        self.verticalLayout_2 = QtGui.QVBoxLayout(self.frame_maincontent)
        self.verticalLayout_2.setSpacing(0)
        self.verticalLayout_2.setMargin(0)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.filelist_splitter = QtGui.QSplitter(self.frame_maincontent)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.filelist_splitter.sizePolicy().hasHeightForWidth())
        self.filelist_splitter.setSizePolicy(sizePolicy)
        self.filelist_splitter.setOrientation(QtCore.Qt.Horizontal)
        self.filelist_splitter.setChildrenCollapsible(False)
        self.filelist_splitter.setObjectName("filelist_splitter")
        self.tableView_filelist = HgFileListView(self.filelist_splitter)
        self.tableView_filelist.setObjectName("tableView_filelist")
        self.frame = QtGui.QFrame(self.filelist_splitter)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame.sizePolicy().hasHeightForWidth())
        self.frame.setSizePolicy(sizePolicy)
        self.frame.setFrameShape(QtGui.QFrame.NoFrame)
        self.frame.setObjectName("frame")
        self.verticalLayout = QtGui.QVBoxLayout(self.frame)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setSizeConstraint(QtGui.QLayout.SetDefaultConstraint)
        self.verticalLayout.setMargin(0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.textview_header = RevDisplay(self.frame)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.textview_header.sizePolicy().hasHeightForWidth())
        self.textview_header.setSizePolicy(sizePolicy)
        self.textview_header.setMinimumSize(QtCore.QSize(0, 0))
        font = QtGui.QFont()
        font.setPointSize(9)
        self.textview_header.setFont(font)
        self.textview_header.setObjectName("textview_header")
        self.verticalLayout.addWidget(self.textview_header)
        self.message_splitter = QtGui.QSplitter(self.frame)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.message_splitter.sizePolicy().hasHeightForWidth())
        self.message_splitter.setSizePolicy(sizePolicy)
        self.message_splitter.setMinimumSize(QtCore.QSize(50, 50))
        self.message_splitter.setFrameShape(QtGui.QFrame.NoFrame)
        self.message_splitter.setLineWidth(0)
        self.message_splitter.setMidLineWidth(0)
        self.message_splitter.setOrientation(QtCore.Qt.Vertical)
        self.message_splitter.setOpaqueResize(True)
        self.message_splitter.setObjectName("message_splitter")
        self.message = RevMessage(self.message_splitter)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.message.sizePolicy().hasHeightForWidth())
        self.message.setSizePolicy(sizePolicy)
        self.message.setMinimumSize(QtCore.QSize(0, 0))
        font = QtGui.QFont()
        font.setFamily("Courier")
        font.setPointSize(9)
        self.message.setFont(font)
        self.message.setObjectName("message")
        self.fileview = HgFileView(self.message_splitter)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.fileview.sizePolicy().hasHeightForWidth())
        self.fileview.setSizePolicy(sizePolicy)
        self.fileview.setMinimumSize(QtCore.QSize(0, 0))
        self.fileview.setObjectName("fileview")
        self.verticalLayout.addWidget(self.message_splitter)
        self.verticalLayout_2.addWidget(self.filelist_splitter)
        self.horizontalLayout.addWidget(self.revisions_splitter)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))

from changeset import RevDisplay, RevMessage
from filelistview import HgFileListView
from fileview import HgFileView
from repoview import HgRepoView
