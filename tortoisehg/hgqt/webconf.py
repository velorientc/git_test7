# webconf.py - Widget to show/edit hgweb config
#
# Copyright 2010 Yuya Nishihara <yuya@tcha.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from tortoisehg.util import hglib, wconfig
from tortoisehg.hgqt import qtlib
from tortoisehg.hgqt.i18n import _
from tortoisehg.hgqt.webconf_ui import Ui_WebconfForm

_FILE_FILTER = _('Config files (*.conf *.config *.ini);;Any files (*)')

# TODO: edit repository map
class WebconfForm(QWidget):
    """Widget to show/edit webconf"""
    def __init__(self, parent=None, webconf=None):
        super(WebconfForm, self).__init__(parent)
        self._qui = Ui_WebconfForm()
        self._qui.setupUi(self)
        self._initicons()
        self._qui.path_edit.currentIndexChanged.connect(self._updateview)

        self.setwebconf(webconf or wconfig.config())
        self._updateform()

    def _initicons(self):
        def setstdicon(w, name):
            w.setIcon(self.style().standardIcon(name))

        setstdicon(self._qui.open_button, QStyle.SP_DialogOpenButton)
        setstdicon(self._qui.save_button, QStyle.SP_DialogSaveButton)
        self._qui.add_button.setIcon(qtlib.geticon('fileadd'))
        self._qui.edit_button.setIcon(qtlib.geticon('fallback'))  # TODO
        self._qui.remove_button.setIcon(qtlib.geticon('filedelete'))

    def setwebconf(self, webconf):
        """set current webconf object"""
        path = hglib.tounicode(getattr(webconf, 'path', None) or '')
        i = self._qui.path_edit.findText(path)
        if i < 0:
            i = 0
            self._qui.path_edit.insertItem(i, path, webconf)
        self._qui.path_edit.setCurrentIndex(i)

    @property
    def webconf(self):
        """current webconf object"""
        def curconf(w):
            i = w.currentIndex()
            _path, conf = unicode(w.itemText(i)), w.itemData(i).toPyObject()
            return conf

        return curconf(self._qui.path_edit)

    @pyqtSlot()
    def _updateview(self):
        m = WebconfModel(config=self.webconf, parent=self)
        self._qui.repos_view.setModel(m)

    def _updateform(self):
        """Update availability of each widget"""
        self._qui.add_button.setEnabled(False)  # TODO
        self._qui.edit_button.setEnabled(False)  # TODO
        self._qui.remove_button.setEnabled(False)  # TODO

    @pyqtSlot()
    def on_open_button_clicked(self):
        path = QFileDialog.getOpenFileName(
            self, _('Open hgweb config'),
            getattr(self.webconf, 'path', None) or '', _FILE_FILTER)
        if path:
            self.openwebconf(path)

    def openwebconf(self, path):
        """load the specified webconf file"""
        path = hglib.fromunicode(path)
        c = wconfig.readfile(path)
        c.path = os.path.abspath(path)
        self.setwebconf(c)

    @pyqtSlot()
    def on_save_button_clicked(self):
        path = QFileDialog.getSaveFileName(
            self, _('Save hgweb config'),
            getattr(self.webconf, 'path', None) or '', _FILE_FILTER)
        if path:
            self.savewebconf(path)

    def savewebconf(self, path):
        """save current webconf to the specified file"""
        path = hglib.fromunicode(path)
        wconfig.writefile(self.webconf, path)
        self.openwebconf(path)  # reopen in case file path changed

class WebconfModel(QAbstractTableModel):
    """Wrapper for webconf object to be a Qt's model object"""
    _COLUMNS = [(_('Path'),),
                (_('Local Path'),)]

    def __init__(self, config, parent=None):
        super(WebconfModel, self).__init__(parent)
        self._config = config

    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            v = self._config.items('paths')[index.row()][index.column()]
            return hglib.tounicode(v)
        return None

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0  # no child
        return len(self._config['paths'])

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0  # no child
        return len(self._COLUMNS)

    def headerData(self, section, orientation, role):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return None
        return self._COLUMNS[section][0]
