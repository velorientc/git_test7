"""Test for encoding helper functions of tortoisehg.util.hglib"""
from nose.tools import *
from tortoisehg.util import hglib

import helpers

JAPANESE_KANA_I = u'\u30a4'  # Japanese katakana "i"

@helpers.with_encoding('utf-8')
def test_none():
    """None shouldn't be touched"""
    for e in ('fromunicode', 'fromutf', 'tounicode', 'toutf'):
        f = getattr(hglib, e)
        assert_equals(None, f(None))


@helpers.with_encoding('utf-8')
def test_fromunicode():
    assert_equals(JAPANESE_KANA_I.encode('utf-8'),
                  hglib.fromunicode(JAPANESE_KANA_I))

@helpers.with_encoding('utf-8')
def test_fromunicode_unicodableobj():
    """fromunicode() accepts unicode-able obj like QString"""
    class Unicodable(object):
        def __unicode__(self):
            return JAPANESE_KANA_I

    assert_equals(JAPANESE_KANA_I.encode('utf-8'),
                  hglib.fromunicode(Unicodable()))

@helpers.with_encoding('ascii', 'utf-8')
def test_fromunicode_fallback():
    assert_equals(JAPANESE_KANA_I.encode('utf-8'),
                  hglib.fromunicode(JAPANESE_KANA_I))

@helpers.with_encoding('ascii')
def test_fromunicode_replace():
    assert_equals('?', hglib.fromunicode(JAPANESE_KANA_I,
                                         errors='replace'))

@helpers.with_encoding('ascii')
def test_fromunicode_strict():
    assert_raises(UnicodeEncodeError,
                  lambda: hglib.fromunicode(JAPANESE_KANA_I))


@helpers.with_encoding('euc-jp')
def test_fromutf():
    assert_equals(JAPANESE_KANA_I.encode('euc-jp'),
                  hglib.fromutf(JAPANESE_KANA_I.encode('utf-8')))

@helpers.with_encoding('ascii', 'euc-jp')
def test_fromutf_fallback():
    assert_equals(JAPANESE_KANA_I.encode('euc-jp'),
                  hglib.fromutf(JAPANESE_KANA_I.encode('utf-8')))

@helpers.with_encoding('ascii')
def test_fromutf_replace():
    assert_equals('?', hglib.fromutf(JAPANESE_KANA_I.encode('utf-8')))


@helpers.with_encoding('euc-jp')
def test_tounicode():
    assert_equals(JAPANESE_KANA_I,
                  hglib.tounicode(JAPANESE_KANA_I.encode('euc-jp')))

@helpers.with_encoding('ascii', 'euc-jp')
def test_tounicode_fallback():
    assert_equals(JAPANESE_KANA_I,
                  hglib.tounicode(JAPANESE_KANA_I.encode('euc-jp')))


@helpers.with_encoding('euc-jp')
def test_toutf():
    assert_equals(JAPANESE_KANA_I.encode('utf-8'),
                  hglib.toutf(JAPANESE_KANA_I.encode('euc-jp')))

@helpers.with_encoding('ascii', 'euc-jp')
def test_toutf_fallback():
    assert_equals(JAPANESE_KANA_I.encode('utf-8'),
                  hglib.toutf(JAPANESE_KANA_I.encode('euc-jp')))


@helpers.with_encoding('ascii')
def test_lossless_unicode_replaced():
    l = hglib.fromunicode(JAPANESE_KANA_I, 'replace')
    assert_equals('?', l)
    assert_equals(JAPANESE_KANA_I, hglib.tounicode(l))

@helpers.with_encoding('euc-jp')
def test_lossless_unicode_double_mapped():
    YEN = u'\u00a5'  # "yen" and "back-slash" are mapped to the same code
    l = hglib.fromunicode(YEN)
    assert_equals('\\', l)
    assert_equals(YEN, hglib.tounicode(l))

@helpers.with_encoding('ascii')
def test_lossless_utf_replaced():
    u = JAPANESE_KANA_I.encode('utf-8')
    l = hglib.fromutf(u)
    assert_equals('?', l)
    assert_equals(u, hglib.toutf(l))

@helpers.with_encoding('ascii')
def test_lossless_utf_cannot_roundtrip():
    u = JAPANESE_KANA_I.encode('cp932')  # bad encoding
    l = hglib.fromutf(u)
    assert_not_equals(u, hglib.toutf(l))
