"""Test for tortoisehg.util.colormap"""
import sys
from nose.tools import *
from tortoisehg.util import colormap

def fakectx(userhash, date, tz=0):
    # AnnotateColorSaturation uses hash() for mapping user to hue
    class user(object):
        def __hash__(self):
            return userhash
    class ctx(object):
        def user(self):
            return user()
        def date(self):
            return (float(date), tz)
        def __repr__(self):
            return '<fakectx:userhash=%x,date=%d,%d>' % (userhash, date, tz)
    return ctx()

def test_user_hue():
    """Is a user mapped to his own color (hue)?"""
    cm = colormap.AnnotateColorSaturation()

    samples = {0x0: '#ffaaaa', 0x1: '#ffaac9', 0x2: '#ffaae9', 0x3: '#f4aaff',
               0x4: '#d4aaff', 0x5: '#b4aaff', 0x6: '#aabfff', 0x7: '#aadfff',
               0x8: '#aaffff', 0x9: '#aaffdf', 0xa: '#aaffbf', 0xb: '#b4ffaa',
               0xc: '#d4ffaa', 0xd: '#f4ffaa', 0xe: '#ffe9aa', 0xf: '#ffc9aa'}
    for i, c in sorted(samples.iteritems(), key=lambda a: a[0]):
        assert_equals(c, cm.get_color(fakectx(sys.maxint / 16 * i, 0), 0))

def test_user_hue_limit():
    cm = colormap.AnnotateColorSaturation(maxhues=8)

    samples = {0x0: '#ffaaaa', 0x1: '#ffaaaa', 0x2: '#ffaae9', 0x3: '#ffaae9',
               0x4: '#d4aaff', 0x5: '#d4aaff', 0x6: '#aabfff', 0x7: '#aabfff',
               0x8: '#aaffff', 0x9: '#aaffff', 0xa: '#aaffbf', 0xb: '#aaffbf',
               0xc: '#d4ffaa', 0xd: '#d4ffaa', 0xe: '#ffe9aa', 0xf: '#ffe9aa'}
    for i, c in sorted(samples.iteritems(), key=lambda a: a[0]):
        assert_equals(c, cm.get_color(fakectx(sys.maxint / 16 * i, 0), 0))

SECS_PER_DAY = 24 * 60 * 60

def test_age_saturation():
    """Is an age mapped to its saturation?"""
    cm = colormap.AnnotateColorSaturation()

    samples = {0: '#ffaaaa', 50: '#ffd4d4', 100: '#ffe2e2', 150: '#ffe9e9',
               200: '#ffeeee', 250: '#fff0f0', 300: '#fff2f2', 350: '#fff4f4',
               400: '#fff5f5', 450: '#fff6f6', 500: '#fff7f7', 550: '#fff7f7'}
    for i, c in sorted(samples.iteritems(), key=lambda a: a[0]):
        assert_equals(c, cm.get_color(fakectx(0, 0), float(i * SECS_PER_DAY)))

def test_age_saturation_limit():
    cm = colormap.AnnotateColorSaturation(maxsaturations=16)

    samples = {0: '#ffaaaa', 3: '#ffaaaa', 4: '#ffafaf', 7: '#ffafaf',
               8: '#ffb4b4', 11: '#ffb4b4', 12: '#ffb9b9', 16: '#ffb9b9',
               17: '#ffbfbf', 22: '#ffbfbf', 23: '#ffc4c4', 29: '#ffc4c4'}
    for i, c in sorted(samples.iteritems(), key=lambda a: a[0]):
        assert_equals(c, cm.get_color(fakectx(0, 0), float(i * SECS_PER_DAY)))

def test_age_calc():
    """Color shouldn't depend on the date but the age"""
    cm = colormap.AnnotateColorSaturation()
    age = 50 * SECS_PER_DAY
    for d in (0, SECS_PER_DAY, 365 * SECS_PER_DAY):
        assert_equals('#ffd4d4', cm.get_color(fakectx(0, d), d + age))

def test_negative_age_calc():
    cm = colormap.AnnotateColorSaturation()
    assert_equals('#ffaaaa', cm.get_color(fakectx(0, 0), 0), '0 days old')
    assert_equals('#ffaaaa', cm.get_color(fakectx(0, 50 * SECS_PER_DAY), 0),
                  '-50 days old (should not raise ZeroDivisionError)')
    assert_equals('#ffaaaa', cm.get_color(fakectx(0, 100 * SECS_PER_DAY), 0),
                  '-100 days old')

def test_makeannotatepalette_latest_wins():
    userstep = sys.maxint / 16
    filectxs = [fakectx(0 * userstep, 0), fakectx(1 * userstep, 1),
                fakectx(2 * userstep, 2), fakectx(3 * userstep, 3),
                fakectx(4 * userstep, 4)]

    palette = colormap.makeannotatepalette(filectxs, now=4, maxcolors=4)
    palfctxs = set()
    for _color, fctxs in palette.iteritems():
        palfctxs.update(fctxs)
    assert_equals(set(filectxs[1:]), palfctxs)

def test_makeannotatepalette_fold_same_color():
    userstep = sys.maxint / 16
    filectxs = [fakectx(0 * userstep, 0), fakectx(1 * userstep, 0),
                fakectx(2 * userstep, 0), fakectx(3 * userstep, 0),
                fakectx(4 * userstep, 0)]
    palette = colormap.makeannotatepalette(filectxs, now=0,
                                           maxcolors=4, maxhues=8)
    assert_equals(3, len(palette))
    assert_equals(set([filectxs[0], filectxs[1]]), set(palette['#ffaaaa']))
    assert_equals(set([filectxs[2], filectxs[3]]), set(palette['#ffaae9']))
    assert_equals(set([filectxs[4]]), set(palette['#d4aaff']))

def test_makeannotatepalette_mindate_included():
    agestep = 10 * SECS_PER_DAY
    filectxs = [fakectx(0, 0 * agestep), fakectx(0, 1 * agestep),
                fakectx(0, 2 * agestep), fakectx(0, 3 * agestep),
                fakectx(0, 4 * agestep), fakectx(0, 5 * agestep),
                fakectx(0, 6 * agestep), fakectx(0, 7 * agestep)]
    palette = colormap.makeannotatepalette(filectxs, now=7 * agestep,
                                           maxcolors=4, maxhues=4,
                                           maxsaturations=255,
                                           mindate=2 * agestep)
    palfctxs = set()
    for _color, fctxs in palette.iteritems():
        palfctxs.update(fctxs)
    for fctx in filectxs[2:]:
        assert fctx in palfctxs

def test_makeannotatepalette_mindate_earlier_than_rev0():
    agestep = 50 * SECS_PER_DAY
    filectxs = [fakectx(0, 1 * agestep), fakectx(0, 2 * agestep)]
    palette = colormap.makeannotatepalette(filectxs, now=2 * agestep,
                                           maxcolors=1, maxhues=1,
                                           maxsaturations=255, mindate=0)
    palfctxs = set()
    for _color, fctxs in palette.iteritems():
        palfctxs.update(fctxs)
    for fctx in filectxs:
        assert fctx in palfctxs
