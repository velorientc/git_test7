# changesetinfo.py - component for displaying changeset summary
#
# Copyright 2009 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

'''component for displaying changeset summary'''

import os
import gtk

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib

from tortoisehg.hgtk import gtklib

def changesetinfo(repo, revid, head=False):
    def lbl(str, bold=True, right=True):
        str = gtklib.markup_escape_text(str)
        label = gtk.Label()
        if bold:
            str = '<b>%s</b>' % str
        label.set_alignment((right and 1 or 0), 0)
        label.set_markup(str)
        return label
    def val(str, bold=False):
        return lbl(str, bold=bold, right=False)

    # prepare data to display
    table = gtklib.LayoutTable()
    table.set_default_paddings(ypad=1)
    ctx = repo[revid]
    revstr = str(ctx.rev())
    summary = ctx.description().replace('\0', '').split('\n')[0][:80]
    node = repo.lookup(revid)
    tags = repo.nodetags(node)

    # construct gtk.Table
    table.add_row(lbl(_('rev')), val(revstr))
    table.add_row(lbl(_('summary')), val(hglib.toutf(summary)))
    table.add_row(lbl(_('user')), val(hglib.toutf(ctx.user())))
    table.add_row(lbl(_('date')), val(hglib.displaytime(ctx.date())))
    table.add_row(lbl(_('branch')), val(hglib.toutf(ctx.branch())))
    if tags:
        table.add_row(lbl(_('tags')), val(hglib.toutf(', '.join(tags))))
    if head and node not in repo.heads():
        table.add_row(None, val(_('Not a head revision!'), bold=True))

    # just for padding
    vbox = gtk.VBox()
    vbox.pack_start(table, True, True, 3)
    hbox = gtk.HBox()
    hbox.pack_start(vbox, True, True, 4)
    return revstr, hbox
