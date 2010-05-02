# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'license.ui'
#
# Created: Mon May 10 22:26:55 2010
#      by: PyQt4 UI code generator 4.7.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_LicenseDialog(object):
    def setupUi(self, LicenseDialog):
        LicenseDialog.setObjectName("LicenseDialog")
        LicenseDialog.setEnabled(True)
        LicenseDialog.resize(458, 360)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(LicenseDialog.sizePolicy().hasHeightForWidth())
        LicenseDialog.setSizePolicy(sizePolicy)
        LicenseDialog.setMaximumSize(QtCore.QSize(16777215, 16777215))
        LicenseDialog.setWhatsThis("None")
        LicenseDialog.setLocale(QtCore.QLocale(QtCore.QLocale.English, QtCore.QLocale.UnitedStates))
        LicenseDialog.setSizeGripEnabled(False)
        LicenseDialog.setModal(True)
        self.verticalLayout = QtGui.QVBoxLayout(LicenseDialog)
        self.verticalLayout.setSizeConstraint(QtGui.QLayout.SetDefaultConstraint)
        self.verticalLayout.setObjectName("verticalLayout")
        self.licenseText = QtGui.QPlainTextEdit(LicenseDialog)
        self.licenseText.setTextInteractionFlags(QtCore.Qt.TextSelectableByKeyboard|QtCore.Qt.TextSelectableByMouse)
        self.licenseText.setObjectName("licenseText")
        self.verticalLayout.addWidget(self.licenseText)
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setContentsMargins(-1, -1, -1, 0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        spacerItem = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.btnClose = QtGui.QPushButton(LicenseDialog)
        self.btnClose.setLocale(QtCore.QLocale(QtCore.QLocale.English, QtCore.QLocale.UnitedStates))
        self.btnClose.setFlat(False)
        self.btnClose.setObjectName("btnClose")
        self.horizontalLayout.addWidget(self.btnClose)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.actionClose = QtGui.QAction(LicenseDialog)
        self.actionClose.setObjectName("actionClose")

        self.retranslateUi(LicenseDialog)
        QtCore.QObject.connect(self.btnClose, QtCore.SIGNAL("clicked()"), LicenseDialog.accept)
        QtCore.QMetaObject.connectSlotsByName(LicenseDialog)

    def retranslateUi(self, LicenseDialog):
        LicenseDialog.setWindowTitle(QtGui.QApplication.translate("LicenseDialog", "License", None, QtGui.QApplication.UnicodeUTF8))
        self.btnClose.setText(QtGui.QApplication.translate("LicenseDialog", "&Close", None, QtGui.QApplication.UnicodeUTF8))
        self.actionClose.setText(QtGui.QApplication.translate("LicenseDialog", "Close", None, QtGui.QApplication.UnicodeUTF8))
        self.actionClose.setToolTip(QtGui.QApplication.translate("LicenseDialog", "Close the License dialog", None, QtGui.QApplication.UnicodeUTF8))

