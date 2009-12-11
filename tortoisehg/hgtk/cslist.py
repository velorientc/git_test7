# cslist.py - embeddable changeset list component
#
# Copyright 2009 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk
import gobject

from mercurial import hg, ui

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths

from tortoisehg.hgtk import csinfo, gtklib

class ChangesetList(gtk.Frame):

    __gsignals__ = {
        'list-updated': (gobject.SIGNAL_RUN_FIRST,
                         gobject.TYPE_NONE,
                         (object, # number of count or None
                          object, # number of total or None
                          bool))  # whether all changesets are shown
    }

    def __init__(self):
        gtk.Frame.__init__(self)
        self.set_shadow_type(gtk.SHADOW_IN)

        # base box
        basebox = gtk.VBox()
        self.add(basebox)

        ## status box
        self.statusbox = statusbox = gtk.HBox()
        basebox.pack_start(statusbox)
        basebox.pack_start(gtk.HSeparator(), False, False, 2)

        # copy form thgstrip.py
        def createlabel():
            label = gtk.Label()
            label.set_alignment(0, 0.5)
            label.set_size_request(-1, 24)
            label.size_request()
            return label

        ### status label
        self.statuslabel = createlabel()
        statusbox.pack_start(self.statuslabel, False, False, 2)

        ### show all button
        self.allbtn = gtk.Button(_('Show all')) # add later

        ### list option
        self.compactopt = gtk.CheckButton(_('Use compact view'))
        statusbox.pack_end(self.compactopt, False, False, 2)

        ## changeset list
        scroll = gtk.ScrolledWindow()
        basebox.add(scroll)
        scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroll.set_size_request(400, 180)
        scroll.size_request()
        self.csbox = gtk.VBox()
        scroll.add_with_viewport(self.csbox)
        scroll.child.set_shadow_type(gtk.SHADOW_NONE)
        self.csbox.set_border_width(4)

        # signal handlers
        self.allbtn.connect('clicked',
            lambda b: self.update(self.curitems, self.currepo, limit=False))
        self.compactopt.connect('toggled',
            lambda b: self.update(self.curitems, self.currepo))

        # csetinfo
        self.lstyle = csinfo.labelstyle(contents=('%(revnum)s:',
                             ' %(branch)s', ' %(tags)s', ' %(summary)s'))
        self.pstyle = csinfo.panelstyle()

        # prepare to show
        self.clear()
        gtklib.idle_add_single_call(self.after_init)

    ### public functions ###

    def update(self, items=None, repo=None, limit=True, queue=False):
        """
        Update changeset list.

        items:   List of revision numbers and/or patch file path.
                 You can pass mixed list.  The order will be respected.
                 If omitted, previous items will be used to show them.
                 Default: None.
        repo:    Repository used to get changeset information.
                 If omitted, previous repo will be used to show them.
                 Default: None.
        limit:   If True, some of changesets will be shown.  Default: True.
        queue:   If True, the update request will be queued to prevent
                 frequent updatings.  In some cases, this option will help
                 to improve UI response.  Default: False.

        return:  True if the list was updated, False if the list wasn't
                 updated.
        """
        # check parameters
        if not items or not repo:
            self.clear()
            return False
        elif queue:
            def timeout(eid, items, repo):
                if self.timeout_queue and self.timeout_queue[-1] == eid[0]:
                    self.update(items, repo, limit, False)
                return False # don't repeat
            event_id = [None]
            event_id[0] = gobject.timeout_add(650, timeout, event_id, items, repo)
            self.timeout_queue.append(event_id[0])
            return False

        self.clear()

        self.curitems = items
        self.currepo = repo

        LIM = 100
        compactview = self.compactopt.get_active()
        style = compactview and self.lstyle or self.pstyle
        factory = csinfo.factory(repo, withupdate=True)

        def add_csinfo(item):
            info = factory(item, style)
            if info.parent:
                info.parent.remove(info)
            self.csbox.pack_start(info, False, False, 2)
        def add_sep():
            if not compactview:
                self.csbox.pack_start(gtk.HSeparator(), False, False)
        def add_snip():
            snipbox = gtk.HBox()
            self.csbox.pack_start(snipbox, False, False, 4)
            spacer = gtk.Label()
            snipbox.pack_start(spacer, False, False)
            spacer.set_width_chars(24)
            sniplbl = gtk.Label()
            snipbox.pack_start(sniplbl, False, False)
            sniplbl.set_markup('<span size="large" weight="heavy"'
                               ' font_family="monospace">...</span>')
            sniplbl.set_angle(90)
            snipbox.pack_start(gtk.Label())

        # determine changesets to show
        numtotal = len(items)
        if limit and numtotal > LIM:
            toshow, lastitem = items[:LIM-1], items[LIM-1:][-1]
        else:
            toshow, lastitem = items, None
        numshow = len(toshow) + (lastitem and 1 or 0)

        # update changeset list
        for r in toshow:
            add_csinfo(r)
            if not r == toshow[-1]: # no need to append to the last
                add_sep()
        if lastitem:
            add_snip()
            add_csinfo(lastitem)
        self.csbox.show_all()

        # update status
        all = self.update_status(numshow, numtotal)

        return True

    def clear(self):
        """ Clear changeset list """
        self.csbox.foreach(lambda c: c.parent.remove(c))
        self.update_status()
        self.curitems = None
        self.currepo = None
        self.timeout_queue = []

    ### internal functions ###

    def after_init(self):
        self.statusbox.pack_start(self.allbtn, False, False, 4)

    def update_status(self, count=None, total=None):
        if count is None or total is None:
            all = button = False
            text = _('No changesets to display')
        else:
            all = count == total
            button = not all
            if all:
                text = _('Displaying all changesets')
            else:
                text = _('Displaying %(count)d of %(total)d changesets') \
                            % dict(count=count, total=total)
        self.statuslabel.set_text(text)
        self.allbtn.set_property('visible', button)
        self.emit('list-updated', count, total, all)
