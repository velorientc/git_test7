# changesetinfo.py - component for displaying changeset summary
#
# Copyright 2009 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

'''component for displaying changeset summary'''

import os
import gtk

from thgutil.i18n import _
from thgutil import hglib

from hggtk import gtklib

def changesetinfo(repo, revid, head=False):
    def lbl(str, bold=False, right=False):
        str = gtklib.markup_escape_text(str)
        label = gtk.Label()
        if bold:
            str = '<b>%s</b>' % str
        label.set_alignment((1 if right else 0), 0)
        label.set_markup(str)
        return label
    def addrow(table, header=None, value=None):
        row = table.get_property('n-rows')
        table.set_property('n-rows', row + 1)
        if header:
            if isinstance(header, str):
                header = lbl(header, True, True)
            table.attach(header, 0, 1, row, row + 1, gtk.FILL, 0, 4, 1)
        if value:
            if isinstance(value, str):
                value = lbl(value)
            table.attach(value, 1, 2, row, row + 1, gtk.FILL|gtk.EXPAND, 0, 4, 1)

    # prepare data to display
    table = gtk.Table(1, 2)
    ctx = repo[revid]
    revstr = str(ctx.rev())
    summary = ctx.description().replace('\0', '').split('\n')[0]
    node = repo.lookup(revid)
    tags = repo.nodetags(node)

    # construct gtk.Table
    addrow(table, _('rev'), revstr)
    addrow(table, _('summary'), hglib.toutf(summary[:80]))
    addrow(table, _('user'), hglib.toutf(ctx.user()))
    addrow(table, _('date'), hglib.displaytime(ctx.date()))
    addrow(table, _('branch'), hglib.toutf(ctx.branch()))
    if tags:
        addrow(table, _('tags'), hglib.toutf(', '.join(tags)))
    if head and node not in repo.heads():
        addrow(table, value=lbl(_('Not a head revision!'), True))

    # just for padding
    vbox = gtk.VBox()
    vbox.pack_start(table, True, True, 3)
    hbox = gtk.HBox()
    hbox.pack_start(vbox, True, True, 4)
    return revstr, hbox
