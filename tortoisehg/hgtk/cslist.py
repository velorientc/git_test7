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

CSL_DND_ID = 1024

class ChangesetList(gtk.Frame):

    __gsignals__ = {
        'list-updated': (gobject.SIGNAL_RUN_FIRST,
                         gobject.TYPE_NONE,
                         (object, # number of count or None
                          object, # number of total or None
                          bool,   # whether all changesets are shown
                          bool))  # whether cslist is updating
    }

    def __init__(self):
        gtk.Frame.__init__(self)
        self.set_shadow_type(gtk.SHADOW_IN)

        self.limit = 20
        self.sel_enable = False

        # dnd variables
        self.dnd_enable = False
        self.hlsep = None
        self.dnd_pb = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, True, 8, 1, 1)
        self.scroll_timer = None

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
        self.scroll = scroll
        scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroll.set_size_request(400, 180)
        scroll.size_request()
        self.csbox = gtk.VBox()
        self.csevent = csevent = gtk.EventBox()
        csevent.add(self.csbox)
        csevent.add_events(gtk.gdk.BUTTON_PRESS_MASK |
                           gtk.gdk.BUTTON_RELEASE_MASK)
        scroll.add_with_viewport(csevent)
        scroll.child.set_shadow_type(gtk.SHADOW_NONE)
        self.csbox.set_border_width(4)

        # signal handlers
        self.allbtn.connect('clicked', lambda b: self.update(self.curitems, \
                self.currepo, limit=False, queue=False))
        self.compactopt.connect('toggled', lambda b: self.update( \
                self.curitems, self.currepo, queue=False, keep=True))

        # dnd setup
        self.dnd_targets = [('thg-dnd', gtk.TARGET_SAME_WIDGET, CSL_DND_ID)]
        csevent.drag_dest_set(gtk.DEST_DEFAULT_MOTION |
                              gtk.DEST_DEFAULT_DROP, self.dnd_targets,
                              gtk.gdk.ACTION_MOVE)
        csevent.connect('drag-begin', self.dnd_begin)
        csevent.connect('drag-end', self.dnd_end)
        csevent.connect('drag-motion', self.dnd_motion)
        csevent.connect('drag-leave', self.dnd_leave)
        csevent.connect('drag-data-received', self.dnd_received)
        csevent.connect('drag-data-get', self.dnd_get)
        csevent.connect('button-press-event', self.button_press)

        # csetinfo
        self.lstyle = csinfo.labelstyle(contents=('%(revnum)s:',
                             ' %(branch)s', ' %(tags)s', ' %(summary)s'))
        self.pstyle = csinfo.panelstyle()

        # prepare to show
        self.clear(noemit=True)
        gtklib.idle_add_single_call(self.after_init)

    ### public functions ###

    def update(self, items=None, repo=None, limit=True, queue=False, **kargs):
        """
        Update changeset list.

        Public arguments:
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

        Internal argument:
        keep:    If True, it keeps previous 'limit' state after refreshing.
                 Note that if you use this, 'limit' value will be ignored
                 and overwritten by previous 'limit' value.  Default: False.

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
            eid = [None]
            eid[0] = gobject.timeout_add(650, timeout, eid, items, repo)
            self.timeout_queue.append(eid[0])
            return False

        # determine whether to keep previous 'limit' state
        if kargs.get('keep', False) and self.has_limit() is False:
            limit = False

        self.clear(noemit=True)

        self.curitems = items
        self.currepo = repo

        compactview = self.compactopt.get_active()
        style = compactview and self.lstyle or self.pstyle
        factory = csinfo.factory(repo, withupdate=True)

        def add_csinfo(item):
            info = factory(item, style)
            if info.parent:
                info.parent.remove(info)
            if self.sel_enable:
                check = gtk.CheckButton()
                check.set_active(True)
                self.chkmap[item] = check
                align = gtk.Alignment(0.5, 0)
                align.add(check)
                hbox = gtk.HBox()
                hbox.pack_start(align, False, False)
                hbox.pack_start(info, False, False)
                info = hbox
            self.csbox.pack_start(info, False, False, 2)
            self.itemmap[item] = info
        def add_sep(show, *keys):
            sep = FixedHSeparator(visible=show)
            self.csbox.pack_start(sep, False, False)
            for key in keys:
                self.sepmap[key] = sep
            return sep
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
            self.item_snip = snipbox

        # determine changesets to show
        numtotal = len(items)
        if limit and self.limit < numtotal:
            toshow, lastitem = items[:self.limit-1], items[self.limit-1:][-1]
        else:
            toshow, lastitem = items, None
        numshow = len(toshow) + (lastitem and 1 or 0)
        self.showitems = toshow + (lastitem and [lastitem] or [])

        def proc():
            # update changeset list
            add_sep(False, 'first', (-1, 0))
            for index, r in enumerate(toshow):
                add_csinfo(r)
                if not r == toshow[-1]:
                    key = (index, index + 1)
                    add_sep(not compactview, key)
            if lastitem:
                add_sep(False, (len(toshow) - 1, len(toshow)))
                add_snip()
                add_sep(False, (numtotal - 2, numtotal - 1))
                add_csinfo(lastitem)
            key = (numtotal - 1, numtotal)
            add_sep(False, 'last', key)
            self.csbox.show_all()

            # update status
            self.update_status(numshow, numtotal)
            self.emit('list-updated', numshow, numtotal,
                      not self.has_limit(), False)

        if numshow < 80:
            proc()
        else:
            self.update_status(message=_('Updating...'))
            self.emit('list-updated', numshow, numtotal,
                      not self.has_limit(), True)
            gtklib.idle_add_single_call(proc)

        return True

    def clear(self, noemit=False):
        """
        Clear changeset list.

        noemit: If True, cslist won't emit 'list-updated' signal.
                Default: False.
        """
        self.csbox.foreach(lambda c: c.parent.remove(c))
        self.update_status()
        if not noemit:
            self.emit('list-updated', None, None, None, None)
        self.curitems = None
        self.showitems = None
        self.currepo = None
        self.timeout_queue = []
        self.itemmap = {}
        self.chkmap = {}
        self.sepmap = {}

    def get_items(self, sel=False):
        """
        Return a list of items or tuples contained 2 values:
        'item' (String) and 'selection state' (Boolean).
        If cslist lists no items, it returns an empty list.

        sel: If True, it returns a list of tuples.  Default: False.
        """
        if self.curitems:
            items = self.curitems
            if not sel:
                return items
            return [(item, self.chkmap[item].get_active()) for item in items]
        return []

    def get_list_limit(self):
        """ Return number of changesets to limit to display """
        return self.limit

    def set_list_limit(self, limit):
        """
        Set number of changesets to limit to display.

        limit: Integer, must be more than 3.  Default: 20.
        """
        if limit < 3:
            limit = 3
        self.limit = limit

    def get_dnd_enable(self):
        """ Return whether drag and drop feature is enabled """
        return self.dnd_enable

    def set_dnd_enable(self, enable):
        """
        Set whether drag and drop feature is enabled.

        enable: Boolean, if True, drag and drop feature will be enabled.
                Default: False.
        """
        self.dnd_enable = enable

    def get_checkbox_enable(self):
        """ Return whether the selection feature is enabled """
        return self.sel_enable

    def set_checkbox_enable(self, enable):
        """
        Set whether the selection feature is enabled.
        When it's enabled, checboxes will be shown in the left of
        changeset panels.

        enable: Boolean, if True, the selection feature will be enabled.
                Default: False.
        """
        self.sel_enable = enable

    def has_limit(self):
        """
        Return whether the list shows all changesets.
        If the list has no changesets, it will return None.
        """
        if self.curitems:
            num = len(self.curitems)
            return self.limit < num and len(self.showitems) != num
        return None

    ### internal functions ###

    def after_init(self):
        self.statusbox.pack_start(self.allbtn, False, False, 4)

        # prepare for auto-scrolling while DnD
        SIZE = 20
        alloc = self.scroll.child.allocation
        self.areas = {}
        def add(name, arg):
            region = gtk.gdk.region_rectangle(arg)
            self.areas[name] = (region, gtk.gdk.Rectangle(*arg))
        add('top', (0, 0, alloc.width, SIZE))
        add('right', (alloc.width - SIZE, 0, SIZE, alloc.height))
        add('bottom', (0, alloc.height - SIZE, alloc.width, SIZE))
        add('left', (0, 0, SIZE, alloc.height))
        add('center', (SIZE, SIZE, alloc.width - 2 * SIZE,
                       alloc.height - 2 * SIZE))

    def update_status(self, count=None, total=None, message=None):
        all = button = False
        if message:
            text = message
        elif count is None or total is None:
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

    def setup_dnd(self, restart=False):
        if not restart and self.scroll_timer is None:
            self.scroll_timer = gobject.timeout_add(25, self.scroll_timeout)
    def teardown_dnd(self, pause=False):
        self.sepmap['first'].set_visible(False)
        self.sepmap['last'].set_visible(False)
        if self.hlsep:
            self.hlsep.drag_unhighlight()
            self.hlsep = None
        if not pause and self.scroll_timer:
            gobject.source_remove(self.scroll_timer)
            self.scroll_timer = None
    def get_drop_pos(self, y):
        first = self.itemmap[self.curitems[0]].allocation
        last = self.itemmap[self.curitems[-1]].allocation
        half = first.height / 2
        num = len(self.curitems)
        if y < first.y + half:
            return -1, 0
        elif last.y + half < y:
            return num - 1, num
        pos = (y - self.item_offset) / float(self.item_unit)
        start = int(pos - 0.5)
        numshow = len(self.showitems)
        if self.has_limit() and numshow - 1 <= pos:
            snip = self.item_snip.allocation
            if y < snip.y + snip.height / 2:
                return numshow - 2, numshow - 1
            else:
                return num - 2, num - 1
        return start, start + 1

    ### signal handlers ###

    def dnd_begin(self, widget, context):
        self.setup_dnd()
        context.set_icon_pixbuf(self.dnd_pb, 0, 0)

    def dnd_end(self, widget, context):
        self.teardown_dnd()

    def dnd_motion(self, widget, context, x, y, event_time):
        if self.item_drag is not None:
            num = len(self.curitems)
            if not self.hlsep:
                self.setup_dnd(restart=True)
            key = self.get_drop_pos(y)
            self.sepmap['first'].set_visible(key == (-1, 0))
            self.sepmap['last'].set_visible(key == (num - 1, num))
            # highlight separator
            sep = self.sepmap[key]
            if self.hlsep != sep:
                if self.hlsep:
                    self.hlsep.drag_unhighlight()
                sep.drag_highlight()
                self.hlsep = sep

    def dnd_leave(self, widget, context, event_time):
        self.teardown_dnd(pause=True)

    def dnd_received(self, widget, context, x, y, sel, target_type, event_time):
        if target_type == CSL_DND_ID:
            items = self.curitems
            start, end = self.get_drop_pos(y)
            pos = self.item_drag
            if start != pos and end != pos:
                item = items[pos]
                items = items[:pos] + items[pos+1:]
                if end < pos:
                    items.insert(end, item)
                else:
                    items.insert(end - 1, item)
                self.update(items, self.currepo, queue=False, keep=True)

    def dnd_get(self, widget, context, sel, target_type, event_time):
        if target_type == CSL_DND_ID and self.item_drag is not None:
            sel.set(sel.target, 8, str(self.curitems[self.item_drag]))

    def button_press(self, widget, event):
        items = self.curitems
        if not self.dnd_enable or not items or len(items) <= 1:
            return
        if event.type == gtk.gdk.BUTTON_PRESS and event.button == 1:
            # get pressed csinfo widget based on pointer position
            first = self.itemmap[items[0]].allocation
            second = self.itemmap[items[1]].allocation
            self.item_offset = first.y
            self.item_unit = second.y - first.y
            pos = int((event.y - self.item_offset) / self.item_unit)
            numshow = len(self.showitems)
            if self.has_limit() and numshow - 1 <= pos:
                last = self.itemmap[items[-1]].allocation
                if last.y < event.y and event.y < (last.y + last.height):
                    pos = len(items) - 1
                else:
                    pos = None
            elif numshow <= pos:
                pos = None
            if pos is not None:
                self.item_drag = pos
                # start dnd
                self.csevent.drag_begin(self.dnd_targets,
                                        gtk.gdk.ACTION_MOVE, 1, event)

    def scroll_timeout(self):
        x, y = self.scroll.get_pointer()
        if not self.areas['center'][0].point_in(x, y):
            def hscroll(left=False, fast=False):
                amount = 2
                if left: amount *= -1
                if fast: amount *= 3
                hadj = self.scroll.get_hadjustment()
                hadj.set_value(hadj.get_value() + amount)
            def vscroll(up=False, fast=False):
                amount = 2
                if up: amount *= -1
                if fast: amount *= 3
                vadj = self.scroll.get_vadjustment()
                vadj.set_value(vadj.get_value() + amount)
            top, topr = self.areas['top']
            bottom, bottomr = self.areas['bottom']
            if y < topr.y:
                vscroll(up=True, fast=True)
            elif top.point_in(x, y):
                vscroll(up=True)
            elif (bottomr.y + bottomr.height) < y:
                vscroll(fast=True)
            elif bottom.point_in(x, y):
                vscroll()
            left, leftr = self.areas['left']
            right, rightr = self.areas['right']
            if x < leftr.x:
                hscroll(left=True, fast=True)
            elif left.point_in(x, y):
                hscroll(left=True)
            elif (rightr.x + rightr.width) < x:
                hscroll(fast=True)
            elif right.point_in(x, y):
                hscroll()
        return True # repeat

class FixedHSeparator(gtk.VBox):

    def __init__(self, visible=True):
        gtk.VBox.__init__(self)
        self.set_size_request(-1, 2)

        self.visible = visible

        self.sep = gtk.HSeparator()
        self.pack_start(self.sep, False, False)
        self.sep.set_no_show_all(not visible)

    def set_visible(self, visible):
        if self.visible != visible:
            self.visible = visible
            self.sep.set_no_show_all(False)
            self.sep.set_property('visible', visible)
            self.sep.set_no_show_all(not visible)
