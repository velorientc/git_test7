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

SECS_PER_DAY = 24 * 60 * 60

def test_age_saturation():
    """Is an age mapped to its saturation?"""
    cm = colormap.AnnotateColorSaturation()

    samples = {0: '#ffaaaa', 50: '#ffd4d4', 100: '#ffe2e2', 150: '#ffe9e9',
               200: '#ffeeee', 250: '#fff0f0', 300: '#fff2f2', 350: '#fff4f4',
               400: '#fff5f5', 450: '#fff6f6', 500: '#fff7f7', 550: '#fff7f7'}
    for i, c in sorted(samples.iteritems(), key=lambda a: a[0]):
        assert_equals(c, cm.get_color(fakectx(0, 0), float(i * SECS_PER_DAY)))

def test_age_calc():
    """Color shouldn't depend on the date but the age"""
    cm = colormap.AnnotateColorSaturation()
    age = 50 * SECS_PER_DAY
    for d in (0, SECS_PER_DAY, 365 * SECS_PER_DAY):
        assert_equals('#ffd4d4', cm.get_color(fakectx(0, d), d + age))
