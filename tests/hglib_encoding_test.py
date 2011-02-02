"""Test for encoding helper functions of tortoisehg.util.hglib"""
from nose.tools import *
from tortoisehg.util import hglib
from tests import with_encoding

JAPANESE_KANA_I = u'\u30a4'  # Japanese katakana "i"

@with_encoding('utf-8')
def test_none():
    """None shouldn't be touched"""
    for e in ('fromunicode', 'fromutf', 'tounicode', 'toutf'):
        f = getattr(hglib, e)
        assert_equals(None, f(None))


@with_encoding('utf-8')
def test_fromunicode():
    assert_equals(JAPANESE_KANA_I.encode('utf-8'),
                  hglib.fromunicode(JAPANESE_KANA_I))

@with_encoding('utf-8')
def test_fromunicode_unicodableobj():
    """fromunicode() accepts unicode-able obj like QString"""
    class Unicodable(object):
        def __unicode__(self):
            return JAPANESE_KANA_I

    assert_equals(JAPANESE_KANA_I.encode('utf-8'),
                  hglib.fromunicode(Unicodable()))

@with_encoding('ascii', 'utf-8')
def test_fromunicode_fallback():
    assert_equals(JAPANESE_KANA_I.encode('utf-8'),
                  hglib.fromunicode(JAPANESE_KANA_I))

@with_encoding('ascii')
def test_fromunicode_replace():
    assert_equals('?', hglib.fromunicode(JAPANESE_KANA_I,
                                         errors='replace'))

@with_encoding('ascii')
def test_fromunicode_strict():
    assert_raises(UnicodeEncodeError,
                  lambda: hglib.fromunicode(JAPANESE_KANA_I))


@with_encoding('euc-jp')
def test_fromutf():
    assert_equals(JAPANESE_KANA_I.encode('euc-jp'),
                  hglib.fromutf(JAPANESE_KANA_I.encode('utf-8')))

@with_encoding('ascii', 'euc-jp')
def test_fromutf_fallback():
    assert_equals(JAPANESE_KANA_I.encode('euc-jp'),
                  hglib.fromutf(JAPANESE_KANA_I.encode('utf-8')))

@with_encoding('ascii')
def test_fromutf_replace():
    assert_equals('?', hglib.fromutf(JAPANESE_KANA_I.encode('utf-8')))


@with_encoding('euc-jp')
def test_tounicode():
    assert_equals(JAPANESE_KANA_I,
                  hglib.tounicode(JAPANESE_KANA_I.encode('euc-jp')))

@with_encoding('ascii', 'euc-jp')
def test_tounicode_fallback():
    assert_equals(JAPANESE_KANA_I,
                  hglib.tounicode(JAPANESE_KANA_I.encode('euc-jp')))


@with_encoding('euc-jp')
def test_toutf():
    assert_equals(JAPANESE_KANA_I.encode('utf-8'),
                  hglib.toutf(JAPANESE_KANA_I.encode('euc-jp')))

@with_encoding('ascii', 'euc-jp')
def test_toutf_fallback():
    assert_equals(JAPANESE_KANA_I.encode('utf-8'),
                  hglib.toutf(JAPANESE_KANA_I.encode('euc-jp')))
