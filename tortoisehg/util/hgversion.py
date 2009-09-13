# hgversion.py - Version information for Mercurial
#
# Copyright 2009 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

try:
    # post 1.1.2
    from mercurial import util
    hgversion = util.version()
except AttributeError:
    # <= 1.1.2
    from mercurial import version
    hgversion = version.get_version()

def checkhgversion(v):
    """range check the Mercurial version"""
    # this is a series of hacks, but Mercurial's versioning scheme
    # doesn't lend itself to a "correct" solution.  This will at least
    # catch people who have old Mercurial packages.
    reqver = ['1', '3']
    if not v or v == 'unknown' or len(v) >= 12:
        # can't make any intelligent decisions about unknown or hashes
        return
    vers = v.split('.')[:2]
    if vers == reqver or len(vers) < 2:
        return
    nextver = list(reqver)
    nextver[1] = chr(ord(reqver[1])+1)
    if vers == nextver:
        return
    return (('This version of TortoiseHg requires Mercurial '
                       'version %s.n to %s.n, but finds %s') %
                       ('.'.join(reqver), '.'.join(nextver), v))
