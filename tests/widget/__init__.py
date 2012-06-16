"""Unit tests of hgqt widgets"""
from nose.plugins.skip import SkipTest
from PyQt4.QtGui import QApplication

def setup():
    if QApplication.type() != QApplication.GuiClient:
        raise SkipTest
