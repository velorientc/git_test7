# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'tortoisehg/hgqt/about.ui'
#
# Created: Tue May 18 19:21:37 2010
#      by: PyQt4 UI code generator 4.7.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_AboutDialog(object):
    def setupUi(self, AboutDialog):
        AboutDialog.setObjectName("AboutDialog")
        AboutDialog.resize(327, 306)
        AboutDialog.setModal(True)
        self.verticalLayout = QtGui.QVBoxLayout(AboutDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.info_vlayout = QtGui.QVBoxLayout()
        self.info_vlayout.setObjectName("info_vlayout")
        self.label_5 = QtGui.QLabel(AboutDialog)
        self.label_5.setText("")
        self.label_5.setObjectName("label_5")
        self.info_vlayout.addWidget(self.label_5)
        self.logo_label = QtGui.QLabel(AboutDialog)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.logo_label.sizePolicy().hasHeightForWidth())
        self.logo_label.setSizePolicy(sizePolicy)
        self.logo_label.setMinimumSize(QtCore.QSize(92, 50))
        self.logo_label.setScaledContents(False)
        self.logo_label.setAlignment(QtCore.Qt.AlignCenter)
        self.logo_label.setObjectName("logo_label")
        self.info_vlayout.addWidget(self.logo_label)
        self.label_6 = QtGui.QLabel(AboutDialog)
        self.label_6.setText("")
        self.label_6.setObjectName("label_6")
        self.info_vlayout.addWidget(self.label_6)
        self.name_version_label = QtGui.QLabel(AboutDialog)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.name_version_label.sizePolicy().hasHeightForWidth())
        self.name_version_label.setSizePolicy(sizePolicy)
        font = QtGui.QFont()
        font.setPointSize(14)
        font.setWeight(75)
        font.setBold(True)
        self.name_version_label.setFont(font)
        self.name_version_label.setAlignment(QtCore.Qt.AlignCenter)
        self.name_version_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.name_version_label.setObjectName("name_version_label")
        self.info_vlayout.addWidget(self.name_version_label)
        self.libs_label = QtGui.QLabel(AboutDialog)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.libs_label.sizePolicy().hasHeightForWidth())
        self.libs_label.setSizePolicy(sizePolicy)
        self.libs_label.setAlignment(QtCore.Qt.AlignCenter)
        self.libs_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.libs_label.setObjectName("libs_label")
        self.info_vlayout.addWidget(self.libs_label)
        self.label_8 = QtGui.QLabel(AboutDialog)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_8.sizePolicy().hasHeightForWidth())
        self.label_8.setSizePolicy(sizePolicy)
        self.label_8.setText("")
        self.label_8.setObjectName("label_8")
        self.info_vlayout.addWidget(self.label_8)
        self.copyright_label = QtGui.QLabel(AboutDialog)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.copyright_label.sizePolicy().hasHeightForWidth())
        self.copyright_label.setSizePolicy(sizePolicy)
        self.copyright_label.setAlignment(QtCore.Qt.AlignCenter)
        self.copyright_label.setObjectName("copyright_label")
        self.info_vlayout.addWidget(self.copyright_label)
        self.courtesy_label = QtGui.QLabel(AboutDialog)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.courtesy_label.sizePolicy().hasHeightForWidth())
        self.courtesy_label.setSizePolicy(sizePolicy)
        self.courtesy_label.setAlignment(QtCore.Qt.AlignCenter)
        self.courtesy_label.setObjectName("courtesy_label")
        self.info_vlayout.addWidget(self.courtesy_label)
        self.label_9 = QtGui.QLabel(AboutDialog)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_9.sizePolicy().hasHeightForWidth())
        self.label_9.setSizePolicy(sizePolicy)
        self.label_9.setText("")
        self.label_9.setObjectName("label_9")
        self.info_vlayout.addWidget(self.label_9)
        self.download_label = QtGui.QLabel(AboutDialog)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.download_label.sizePolicy().hasHeightForWidth())
        self.download_label.setSizePolicy(sizePolicy)
        self.download_label.setAlignment(QtCore.Qt.AlignCenter)
        self.download_label.setObjectName("download_label")
        self.info_vlayout.addWidget(self.download_label)
        self.download_url_label = QtGui.QLabel(AboutDialog)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.download_url_label.sizePolicy().hasHeightForWidth())
        self.download_url_label.setSizePolicy(sizePolicy)
        self.download_url_label.setMouseTracking(True)
        self.download_url_label.setAlignment(QtCore.Qt.AlignCenter)
        self.download_url_label.setObjectName("download_url_label")
        self.info_vlayout.addWidget(self.download_url_label)
        self.label_10 = QtGui.QLabel(AboutDialog)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_10.sizePolicy().hasHeightForWidth())
        self.label_10.setSizePolicy(sizePolicy)
        self.label_10.setText("")
        self.label_10.setObjectName("label_10")
        self.info_vlayout.addWidget(self.label_10)
        self.verticalLayout.addLayout(self.info_vlayout)
        self.button_hlayout = QtGui.QHBoxLayout()
        self.button_hlayout.setObjectName("button_hlayout")
        self.license_button = QtGui.QPushButton(AboutDialog)
        self.license_button.setObjectName("license_button")
        self.button_hlayout.addWidget(self.license_button)
        spacerItem = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.button_hlayout.addItem(spacerItem)
        self.close_button = QtGui.QPushButton(AboutDialog)
        self.close_button.setObjectName("close_button")
        self.button_hlayout.addWidget(self.close_button)
        self.verticalLayout.addLayout(self.button_hlayout)
        self.actionVisitDownloadSite = QtGui.QAction(AboutDialog)
        self.actionVisitDownloadSite.setCheckable(True)
        self.actionVisitDownloadSite.setObjectName("actionVisitDownloadSite")
        self.actionShowLicense = QtGui.QAction(AboutDialog)
        self.actionShowLicense.setCheckable(True)
        self.actionShowLicense.setObjectName("actionShowLicense")

        self.retranslateUi(AboutDialog)
        QtCore.QObject.connect(self.close_button, QtCore.SIGNAL("clicked()"), AboutDialog.close)
        QtCore.QObject.connect(self.license_button, QtCore.SIGNAL("clicked()"), AboutDialog.actionShowLicense)
        QtCore.QObject.connect(self.download_url_label, QtCore.SIGNAL("linkActivated(QString)"), AboutDialog.actionVisitDownloadSite)
        QtCore.QMetaObject.connectSlotsByName(AboutDialog)

    def retranslateUi(self, AboutDialog):
        AboutDialog.setWindowTitle(QtGui.QApplication.translate("AboutDialog", "Dialog", None, QtGui.QApplication.UnicodeUTF8))
        self.logo_label.setText(QtGui.QApplication.translate("AboutDialog", "thg logo", None, QtGui.QApplication.UnicodeUTF8))
        self.name_version_label.setText(QtGui.QApplication.translate("AboutDialog", "TortoiseHg (version %s)", None, QtGui.QApplication.UnicodeUTF8))
        self.libs_label.setText(QtGui.QApplication.translate("AboutDialog", "with Mercurial-%s, Python-%s, PyQt4-%s, Qt-%s", None, QtGui.QApplication.UnicodeUTF8))
        self.copyright_label.setText(QtGui.QApplication.translate("AboutDialog", "Copyright 2008-2010 Steve Borho and  others", None, QtGui.QApplication.UnicodeUTF8))
        self.courtesy_label.setText(QtGui.QApplication.translate("AboutDialog", "Several icons are courtesy of the TortoiseSVN project", None, QtGui.QApplication.UnicodeUTF8))
        self.download_label.setText(QtGui.QApplication.translate("AboutDialog", "A new version of TortoiseHg is ready for download!", None, QtGui.QApplication.UnicodeUTF8))
        self.download_url_label.setText(QtGui.QApplication.translate("AboutDialog", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><a href=\"http://thg_download_url\"><span style=\" text-decoration: underline; color:#0000ff;\">http://thg-download-url</span></a></p></body></html>", None, QtGui.QApplication.UnicodeUTF8))
        self.license_button.setText(QtGui.QApplication.translate("AboutDialog", "&License", None, QtGui.QApplication.UnicodeUTF8))
        self.close_button.setText(QtGui.QApplication.translate("AboutDialog", "&Close", None, QtGui.QApplication.UnicodeUTF8))
        self.actionVisitDownloadSite.setText(QtGui.QApplication.translate("AboutDialog", "visitDownloadSite", None, QtGui.QApplication.UnicodeUTF8))
        self.actionShowLicense.setText(QtGui.QApplication.translate("AboutDialog", "showLicense", None, QtGui.QApplication.UnicodeUTF8))

