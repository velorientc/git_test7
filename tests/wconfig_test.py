import os, tempfile, shutil
from nose.tools import *
from nose.plugins.skip import SkipTest
from StringIO import StringIO
from mercurial import config
from tortoisehg.util import wconfig

def setup():
    global _tempdir
    _tempdir = tempfile.mkdtemp()

def teardown():
    shutil.rmtree(_tempdir)


def newrconfig(vals={}):
    c = config.config()
    for k, v in isinstance(vals, dict) and vals.iteritems() or vals:
        sec, it = k.split('.', 1)
        c.set(sec, it, v)
    return c

def newwconfig(vals={}):
    return wconfig.config(newrconfig(vals))

def written(c):
    dest = StringIO()
    c.write(dest)
    return dest.getvalue()

def writetempfile(s):
    fd, path = tempfile.mkstemp(dir=_tempdir)
    os.write(fd, s)
    os.close(fd)
    return path

class _Collector(list):
    def __call__(self, func):
        self.append(func)
        return func

with_rconfig = _Collector()
with_wconfig = _Collector()
with_both = _Collector()


def test_both():
    for e in with_wconfig + with_both:
        if wconfig._hasiniparse:
            yield e
        else:
            def skipped():
                raise SkipTest
            yield skipped

    orighasiniparse = wconfig._hasiniparse
    wconfig._hasiniparse = False
    try:
        for e in with_rconfig + with_both:
            yield e
    finally:
        wconfig._hasiniparse = orighasiniparse


@with_both
def check_copy():
    c = newwconfig({'foo.bar': 'baz'})
    assert_equals(c.__class__, c.copy().__class__)
    assert_equals('baz', c.copy().get('foo', 'bar'))

@with_both
def check_contains():
    c = newwconfig({'foo.bar': 'baz'})
    assert 'foo' in c
    assert 'bar' not in c

@with_both
def check_getitem():
    c = newwconfig({'foo.bar': 'x', 'foo.baz': 'y'})
    assert_equals({'bar': 'x', 'baz': 'y'}, dict(c['foo']))
    assert_equals({}, dict(c['unknown']))

@with_both
def check_getitem_empty_then_set_no_effect():
    c = newwconfig()
    c['unknown']['bar'] = 'baz'
    assert not c.get('unknown', 'bar')

@with_both
def check_set_followed_by_getitem_empty():
    c = newwconfig()
    c['unknown']
    c.set('unknown', 'foo', 'bar')
    assert_equals('bar', c.get('unknown', 'foo'))
    assert_equals('bar', c['unknown']['foo'])

@with_both
def check_dict_contains():
    c = newwconfig({'foo.bar': 'x'})
    assert 'bar' in c['foo']
    assert 'baz' not in c['foo']

@with_both
def check_dict_getitem():
    c = newwconfig({'foo.bar': 'x'})
    assert_equals('x', c['foo']['bar'])
    assert_raises(KeyError, lambda: c['foo']['baz'])

@with_both
def check_dict_setitem():
    c = newwconfig({'foo.bar': 'x'})
    c['foo']['bar'] = 'y'
    c['foo']['baz'] = 'z'
    assert_equals('y', c['foo']['bar'])
    assert_equals('z', c['foo']['baz'])

@with_wconfig  # original config doesn't preserve the order
def check_dict_setitem_preserve_order():
    c = newwconfig([('foo.bar', 'x'), ('foo.baz', 'y')])
    assert_equals(['bar', 'baz'], list(c['foo']))
    c['foo']['bar'] = 'z'
    assert_equals(['bar', 'baz'], list(c['foo']))

@with_both
def check_dict_iter():
    c = newwconfig({'foo.bar': 'x', 'foo.baz': 'y'})
    assert_equals(set(['bar', 'baz']), set(c['foo']))

@with_both
def check_dict_len():
    c = newwconfig({'foo.bar': 'x'})
    assert_equals(1, len(c['foo']))

@with_both
def check_dict_update():
    c = newwconfig({'foo.bar': 'x', 'foo.baz': 'y'})
    c['foo'].update(newwconfig({'foo.bar': 'z', 'foo.baz': 'w'})['foo'])
    assert_equals('z', c['foo']['bar'])
    assert_equals('w', c['foo']['baz'])

@with_both
def check_dict_delitem():
    c = newwconfig({'foo.bar': 'x'})
    del c['foo']['bar']
    assert 'bar' not in c['foo']

@with_both
def check_iter():
    c = newwconfig({'foo.bar': 'x', 'baz.bax': 'y'})
    assert_equals(set(['foo', 'baz']), set(c))

@with_both
def check_update():
    c0 = newwconfig({'foo.bar': 'x', 'foo.blah': 'w'})
    c1 = newwconfig({'foo.bar': 'y', 'baz.bax': 'z'})
    c0.update(c1)
    assert_equals('y', c0.get('foo', 'bar'))
    assert_equals('z', c0.get('baz', 'bax'))
    assert_equals('w', c0.get('foo', 'blah'))

@with_both
def check_get():
    c = newwconfig({'foo.bar': 'baz'})
    assert_equals('baz', c.get('foo', 'bar'))
    assert_equals(None, c.get('foo', 'baz'))
    assert_equals('x', c.get('foo', 'baz', 'x'))

@with_both
def check_source():
    c = newwconfig()
    c.set('foo', 'bar', 'baz', source='blah')
    assert_equals('blah', c.source('foo', 'bar'))

@with_both
def check_sections():
    c = newwconfig({'foo.bar': 'x', 'baz.bax': 'y'})
    assert_equals(['baz', 'foo'], c.sections())

@with_both
def check_items():
    c = newwconfig({'foo.bar': 'x', 'foo.baz': 'y'})
    assert_equals({'bar': 'x', 'baz': 'y'}, dict(c.items('foo')))

@with_both
def check_set():
    c = newwconfig({'foo.bar': 'x'})
    c.set('foo', 'baz', 'y')
    c.set('foo', 'bar', 'w')
    c.set('newsection', 'bax', 'z')
    assert_equals('y', c.get('foo', 'baz'))
    assert_equals('w', c.get('foo', 'bar'))
    assert_equals('z', c.get('newsection', 'bax'))

@with_wconfig  # original config doesn't preserve the order
def check_set_preserve_order():
    c = newwconfig([('foo.bar', 'x'), ('foo.baz', 'y')])
    assert_equals(['bar', 'baz'], list(c['foo']))
    c.set('foo', 'bar', 'z')
    assert_equals(['bar', 'baz'], list(c['foo']))

# TODO: test_parse
# TODO: test_read

@with_wconfig
def check_write_after_set():
    c = newwconfig()
    c.set('foo', 'bar', 'baz')
    assert_equals('[foo]\nbar = baz', written(c).rstrip())

@with_wconfig
def check_write_empty():
    c = newwconfig()
    assert_equals('', written(c).rstrip())

@with_wconfig
def check_write_after_update():
    c = newwconfig()
    c.update(newwconfig({'foo.bar': 'baz'}))
    assert_equals('[foo]\nbar = baz', written(c).rstrip())

@with_wconfig
def check_read_write():
    c = newwconfig()
    s = '[foo]\nbar = baz'
    c.read(path='foo', fp=StringIO(s))
    assert_equals(s, written(c).rstrip())

@with_wconfig
def check_write_after_dict_setitem():
    c = newwconfig({'foo.bar': 'x'})
    c['foo']['bar'] = 'y'
    assert_equals('[foo]\nbar = y', written(c).rstrip())

@with_wconfig
def check_write_after_dict_update():
    c = newwconfig({'foo.bar': 'x'})
    c['foo'].update({'bar': 'y'})
    assert_equals('[foo]\nbar = y', written(c).rstrip())

@with_wconfig
def check_write_after_dict_delitem():
    c = newwconfig({'foo.bar': 'x', 'foo.baz': 'y'})
    del c['foo']['bar']
    assert_equals('[foo]\nbaz = y', written(c).rstrip())

@with_wconfig
def check_read_write_rem():
    c = newwconfig()
    s = '[foo]\nrem = x'
    c.read(path='foo', fp=StringIO(s))
    c.set('foo', 'rem', 'y')
    assert_equals('[foo]\nrem = y', written(c).rstrip())


@with_wconfig
def check_write_conflict_set_set():
    fname = writetempfile('[foo]\nbar = x')
    c0 = wconfig.readfile(fname)
    c1 = wconfig.readfile(fname)
    c1.set('foo', 'bar', 'y')
    wconfig.writefile(c1, fname)
    c0.set('foo', 'bar', 'z')
    wconfig.writefile(c0, fname)

    cr = wconfig.readfile(fname)
    assert_equals('z', cr.get('foo', 'bar'))

@with_wconfig
def check_write_conflict_del_set():
    fname = writetempfile('[foo]\nbar = x')
    c0 = wconfig.readfile(fname)
    c1 = wconfig.readfile(fname)
    del c1['foo']['bar']
    wconfig.writefile(c1, fname)
    c0.set('foo', 'bar', 'z')
    wconfig.writefile(c0, fname)

    cr = wconfig.readfile(fname)
    assert_equals('z', cr.get('foo', 'bar'))

@with_wconfig
def check_write_conflict_set_del():
    fname = writetempfile('[foo]\nbar = x')
    c0 = wconfig.readfile(fname)
    c1 = wconfig.readfile(fname)
    c1.set('foo', 'bar', 'y')
    wconfig.writefile(c1, fname)
    del c0['foo']['bar']
    wconfig.writefile(c0, fname)

    cr = wconfig.readfile(fname)
    assert not cr.get('foo', 'bar')

@with_wconfig
def check_write_conflict_del_del():
    fname = writetempfile('[foo]\nbar = x')
    c0 = wconfig.readfile(fname)
    c1 = wconfig.readfile(fname)
    del c1['foo']['bar']
    wconfig.writefile(c1, fname)
    del c0['foo']['bar']
    wconfig.writefile(c0, fname)  # shouldn't raise KeyError

    cr = wconfig.readfile(fname)
    assert not cr.get('foo', 'bar')

@with_wconfig
def check_write_noconflict_set_set():
    fname = writetempfile('[foo]\nbar = x')
    c0 = wconfig.readfile(fname)
    c1 = wconfig.readfile(fname)
    c1.set('foo', 'baz', 'y')
    wconfig.writefile(c1, fname)
    c0.set('foo', 'bar', 'z')
    wconfig.writefile(c0, fname)  # should not override foo.baz = y

    cr = wconfig.readfile(fname)
    assert_equals('z', cr.get('foo', 'bar'))
    assert_equals('y', cr.get('foo', 'baz'))
    assert not c0.get('foo', 'baz')  # don't reload c1's change implicitly

@with_wconfig
def check_write_noconflict_del():
    fname = writetempfile('[foo]\nbar = x')
    c0 = wconfig.readfile(fname)
    c1 = wconfig.readfile(fname)
    del c1['foo']['bar']
    wconfig.writefile(c1, fname)
    wconfig.writefile(c0, fname)  # shouldn't override del foo.bar

    cr = wconfig.readfile(fname)
    assert not cr.get('foo', 'bar')
    assert c0.get('foo', 'bar')  # don't reload c1's change implicitly


@with_wconfig
def check_write_copied():
    fname = writetempfile('[foo]\nbar = x')
    c0 = wconfig.readfile(fname)
    c1 = c0.copy()
    c1.set('foo', 'baz', 'y')
    wconfig.writefile(c1, fname)

    cr = wconfig.readfile(fname)
    assert_equals('x', cr.get('foo', 'bar'))
    assert_equals('y', cr.get('foo', 'baz'))

@with_wconfig
def check_write_copied_conflict():
    fname = writetempfile('[foo]\nbar = x')
    c0 = wconfig.readfile(fname)
    c1 = c0.copy()
    c0.set('foo', 'bar', 'y')
    wconfig.writefile(c0, fname)
    wconfig.writefile(c1, fname)  # shouldn't override foo.bar = y

    cr = wconfig.readfile(fname)
    assert_equals('y', cr.get('foo', 'bar'))

@with_wconfig
def test_write_copied_rconfig():
    c0 = newrconfig({'foo.bar': 'x'})
    c1 = wconfig.config(c0)
    assert_equals('[foo]\nbar = x', written(c1).rstrip())

@with_both
def check_readfile():
    fname = writetempfile('[foo]\nbar = baz')
    c = wconfig.readfile(fname)
    assert_equals('baz', c.get('foo', 'bar'))

@with_wconfig
def check_writefile():
    c = newwconfig({'foo.bar': 'baz'})
    fname = writetempfile('')
    wconfig.writefile(c, fname)
    assert_equals('[foo]\nbar = baz', open(fname).read().rstrip())
