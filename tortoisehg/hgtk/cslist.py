# cslist.py - embeddable changeset/patch list component
#
# Copyright 2009 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import gobject

from mercurial import hg, ui

from tortoisehg.util.i18n import _
from tortoisehg.util import hglib, paths

from tortoisehg.hgtk import csinfo, gtklib

CSL_DND_ITEM     = 1024
CSL_DND_URI_LIST = 1025

ASYNC_LIMIT = 60

class ChangesetList(gtk.Frame):

    __gsignals__ = {
        'list-updated': (gobject.SIGNAL_RUN_FIRST,
                         gobject.TYPE_NONE,
                         (object, # number of all items or None
                          object, # number of selections or None
                          object, # number of showings or None
                          bool)), # whether cslist is updating
        'files-dropped': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          (object, # list of dropped files
                           str)),  # raw string data
        'item-activated': (gobject.SIGNAL_RUN_FIRST,
                           gobject.TYPE_NONE,
                           (str,     # revision number or patch file path
                            object)) # reference of csinfo widget
    }

    def __init__(self):
        gtk.Frame.__init__(self)
        self.set_shadow_type(gtk.SHADOW_IN)

        # member variables
        self.curitems = None
        self.currepo = None
        self.showitems = None
        self.chkmap = {}
        self.limit = 20
        self.curfactory = None

        self.timeout_queue = []
        self.sel_enable = False
        self.dnd_enable = False
        self.act_enable = False

        # dnd variables
        self.itemmap = {}
        self.hlsep = None
        self.dnd_pb = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, True, 8, 1, 1)
        self.scroll_timer = None

        # base box
        basebox = gtk.VBox()
        self.add(basebox)

        ## status box
        self.statusbox = statusbox = gtk.HBox()
        basebox.pack_start(statusbox, False, False)
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

        ## item list
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
        self.allbtn.connect('clicked', lambda b: self.expand_items())
        self.compactopt.connect('toggled', lambda b: self.update( \
                self.curitems, self.currepo, queue=False, keep=True))

        # dnd setup
        self.dnd_targets = [('thg-dnd', gtk.TARGET_SAME_WIDGET, CSL_DND_ITEM)]
        targets = self.dnd_targets + [('text/uri-list', 0, CSL_DND_URI_LIST)]
        csevent.drag_dest_set(gtk.DEST_DEFAULT_MOTION | gtk.DEST_DEFAULT_DROP,
                              targets, gtk.gdk.ACTION_MOVE)
        csevent.connect('drag-begin', self.dnd_begin)
        csevent.connect('drag-end', self.dnd_end)
        csevent.connect('drag-motion', self.dnd_motion)
        csevent.connect('drag-leave', self.dnd_leave)
        csevent.connect('drag-data-received', self.dnd_received)
        csevent.connect('drag-data-get', self.dnd_get)
        csevent.connect('button-press-event', self.button_press)

        # csetinfo
        def data_func(widget, item, ctx):
            if item in ('item', 'item_l'):
                if not isinstance(ctx, csinfo.patchctx):
                    return True # dummy
                revid = widget.get_data('revid')
                if not revid:
                    return widget.target
                filename = os.path.basename(widget.target)
                return filename, revid
            raise csinfo.UnknownItem(item)
        def label_func(widget, item):
            if item in ('item', 'item_l'):
                if not isinstance(widget.ctx, csinfo.patchctx):
                    return _('Revision:')
                return _('Patch:')
            raise csinfo.UnknownItem(item)
        def markup_func(widget, item, value):
            if item in ('item', 'item_l'):
                if not isinstance(widget.ctx, csinfo.patchctx):
                    if item == 'item':
                        return widget.get_markup('rev')
                    return widget.get_markup('revnum')
                mono = dict(face='monospace', size='9000')
                if isinstance(value, basestring):
                    return gtklib.markup(value, **mono)
                filename = gtklib.markup(value[0])
                revid = gtklib.markup(value[1], **mono)
                if item == 'item':
                    return '%s (%s)' % (filename, revid)
                return filename
            raise csinfo.UnknownItem(item)
        self.custom = csinfo.custom(data=data_func, label=label_func,
                                    markup=markup_func)
        self.lstyle = csinfo.labelstyle(
                             contents=('%(item_l)s:', ' %(branch)s',
                                       ' %(tags)s', ' %(summary)s'))
        self.pstyle = csinfo.panelstyle(
                             contents=('item', 'summary', 'user','dateage',
                                       'rawbranch', 'tags', 'transplant',
                                       'p4', 'svn'))

        # prepare to show
        gtklib.idle_add_single_call(self.after_init)

    ### public functions ###

    def update(self, items=None, repo=None, limit=True, queue=False, **kargs):
        """
        Update the item list.

        Public arguments:
        items: List of revision numbers and/or patch file path.
               You can pass mixed list.  The order will be respected.
               If omitted, previous items will be used to show them.
               Default: None.
        repo: Repository used to get changeset information.
              If omitted, previous repo will be used to show them.
              Default: None.
        limit: If True, some of items will be shown.  Default: True.
        queue: If True, the update request will be queued to prevent
               frequent updatings.  In some cases, this option will help
               to improve UI response.  Default: False.

        Internal argument:
        keep: If True, it keeps previous selection states and 'limit' value
              after refreshing.  Note that if you use 'limit' and this options
              at the same time, 'limit' value is used against previous value.
              Default: False.

        return: True if the item list was updated successfully,
                False if it wasn't updated.
        """
        # check parameters
        if not items or not repo:
            self.clear()
            return False
        elif queue:
            def timeout(eid, items, repo):
                if self.timeout_queue and self.timeout_queue[-1] == eid[0]:
                    self.timeout_queue = []
                    self.update(items, repo, limit, False)
                return False # don't repeat
            eid = [None]
            eid[0] = gobject.timeout_add(650, timeout, eid, items, repo)
            self.timeout_queue.append(eid[0])
            return False

        # determine whether to keep previous 'limit' state
        if kargs.get('keep', False) and self.has_limit() is False:
            limit = False

        # initialize variables
        self.curitems = items
        self.currepo = repo
        self.itemmap = {}

        if self.sel_enable and not kargs.get('keep', False):
            self.chkmap = {}
            for item in items:
                self.chkmap[item] = True

        # determine items to show
        numtotal = len(items)
        if limit and self.limit < numtotal:
            toshow, lastitem = items[:self.limit-1], items[-1]
        else:
            toshow, lastitem = items, None
        numshow = len(toshow) + (lastitem and 1 or 0)
        self.showitems = toshow + (lastitem and [lastitem] or [])

        # prepare to update item list
        self.curfactory = csinfo.factory(repo, self.custom, withupdate=True)

        def add_sep():
            sep = self.create_sep()
            self.csbox.pack_start(sep, False, False)

        # clear item list
        self.csbox.foreach(lambda c: c.parent.remove(c))

        # update item list
        def proc():
            # add csinfo widgets
            for index, r in enumerate(toshow):
                self.add_csinfo(r)
            if lastitem:
                self.add_snip()
                self.add_csinfo(lastitem)
            add_sep()
            self.csbox.show_all()

            # show/hide separators
            self.update_seps()

            # update status
            self.update_status()

        # determine doing it now or later
        if numshow < ASYNC_LIMIT:
            proc()
        else:
            self.update_status(updating=True)
            gtklib.idle_add_single_call(proc)

        return True

    def clear(self):
        """ Clear the item list  """
        self.csbox.foreach(lambda c: c.parent.remove(c))
        self.curitems = None
        self.update_status()

    def get_items(self, sel=False):
        """
        Return a list of items or tuples contained 2 values:
        'item' (String) and 'selection state' (Boolean).
        If cslist lists no items, it returns an empty list.

        sel: If True, it returns a list of tuples.  Default: False.
        """
        items = self.curitems
        if items:
            if not sel:
                return items
            return [(item, self.chkmap[item]) for item in items]
        return []

    def get_list_limit(self):
        """ Return number of items to limit to display """
        return self.limit

    def set_list_limit(self, limit):
        """
        Set number of items to limit to display.

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
        When it's enabled, checboxes will be placed at the left of
        csinfo widgets.

        enable: Boolean, if True, the selection feature will be enabled.
                Default: False.
        """
        self.sel_enable = enable

    def get_activatable_enable(self):
        """ Return whether items are activatable """
        return self.act_enable

    def set_activatable_enable(self, enable):
        """
        Set whether items are activatable.
        By enabling this, items in the list will be emitted 'item-activated'
        signal when the user double-clicked on the list.

        enable: Boolean, if True, items will be selectable.  Default: False.
        """
        self.act_enable = enable

    def get_compact_view(self):
        """ Return whether the compact view is enabled """
        return self.compactopt.get_active()

    def set_compact_view(self, compact):
        """
        Set whether the compact view is enabled.

        enable: Boolean, if True, the compact view will be enabled.
                Default: False.
        """
        self.compactopt.set_active(compact)

    def has_limit(self):
        """
        Return whether the item list shows all items.
        If the item list has no items, it will return None.
        """
        if self.curitems:
            num = len(self.curitems)
            return self.limit < num and len(self.showitems) != num
        return None

    ### internal functions ###

    def after_init(self):
        self.statusbox.pack_start(self.allbtn, False, False, 4)

    def update_status(self, updating=False):
        numshow = numsel = numtotal = all = None
        if self.curitems is None:
            button = False
            text = _('No items to display')
        else:
            # prepare data
            numshow, numtotal = len(self.showitems), len(self.curitems)
            data = dict(count=numshow, total=numtotal)
            if self.sel_enable:
                items = self.get_items(sel=True)
                numsel = len([item for item, sel in items if sel])
                data['sel'] = numsel
            all = data['count'] == data['total']
            button = not all
            # generate status text
            if updating:
                text = _('Updating...')
            elif self.sel_enable:
                if all:
                    text = _('Selecting %(sel)d of %(total)d, displaying '
                             'all items') % data
                else:
                    text = _('Selecting %(sel)d, displaying %(count)d of '
                             '%(total)d items') % data
            else:
                if all:
                    text = _('Displaying all items')
                else:
                    text = _('Displaying %(count)d of %(total)d items') % data
        self.statuslabel.set_text(text)
        self.allbtn.set_property('visible', button)
        self.emit('list-updated', numtotal, numsel, numshow, updating)

    def setup_dnd(self, restart=False):
        if not restart and self.scroll_timer is None:
            self.scroll_timer = gobject.timeout_add(25, self.scroll_timeout)

    def teardown_dnd(self, pause=False):
        first = self.get_sep(0)
        if first:
            first.set_visible(False)
        last = self.get_sep(-1)
        if last:
            last.set_visible(False)
        if self.hlsep:
            self.hlsep.drag_unhighlight()
            self.hlsep = None
        if not pause and self.scroll_timer:
            gobject.source_remove(self.scroll_timer)
            self.scroll_timer = None

    def get_item_pos(self, y, detail=False):
        pos = None
        items = self.curitems
        num = len(items)
        numshow = len(self.showitems)
        first = self.itemmap[items[0]]
        beforesnip = self.itemmap[items[numshow - 2]]
        snip = self.has_limit() and self.itemmap['snip'] or None
        last = self.itemmap[items[-1]]
        def calc_ratio(geom):
            return (y - geom['y']) / float(geom['height'])
        if y < first['y']:
            start, end = -1, 0
        elif last['bottom'] < y:
            start, end = num - 1, num
        elif snip and beforesnip['bottom'] < y and y < last['y']:
            ratio = calc_ratio(snip)
            if ratio < 0.5:
                start, end = numshow - 2, numshow - 1
            else:
                start, end = num - 2, num - 1
        else:
            # calc item showitems pos (binary search)
            def mid(start, end):
                return (start + end) / 2
            start, end = 0, numshow - 1
            pos = mid(start, end)
            while start < end:
                data = self.itemmap[self.showitems[pos]]
                if y < data['y']:
                    end = pos - 1
                elif data['bottom'] < y:
                    start = pos + 1
                else:
                    break
                pos = mid(start, end)
            # translate to curitems pos
            pos = self.trans_to_cur(pos)
            # calc detailed pos if need
            if detail:
                data = self.itemmap[items[pos]]
                ratio = calc_ratio(data)
                if ratio < 0.5:
                    start, end = pos - 1, pos
                else:
                    start, end = pos, pos + 1
        if detail:
            return pos, start, end
        return pos

    def get_sep(self, pos):
        """
        pos: Number, the position of separator you need.
             If -1 or list length, indicates the last separator.
        """
        # invalid position/condition
        if pos < -1 or not self.showitems:
            return None
        def get_last():
            child = self.csbox.get_children()[-1]
            return isinstance(child, FixedHSeparator) and child or None
        # last separator
        if pos == -1:
            return get_last()
        # limiting case
        if self.has_limit():
            # snip box separator
            if pos == self.limit - 1:
                return self.itemmap['snip']['sep']
            # list length (+ snip box)
            if pos == self.limit + 1:
                return get_last()
            # separators after snip box
            if self.limit - 1 < pos:
                return self.itemmap[self.showitems[pos-1]]['sep']
        # list length
        elif pos == len(self.showitems):
            return get_last()
        # others
        return self.itemmap[self.showitems[pos]]['sep']

    def get_sep_by_y(self, y):
        pos, start, end = self.get_item_pos(y, detail=True)
        if self.has_limit() and self.limit - 1 < end:
            end -= len(self.curitems) - self.limit - 1
        return self.get_sep(end)

    def update_seps(self):
        """ Update visibility of all separators """
        compact = self.get_compact_view()
        for item in self.showitems[1:]:
            sep = self.itemmap[item]['sep']
            sep.set_visible(not compact)
        if self.has_limit():
            self.itemmap['snip']['sep'].set_visible(False)
            self.itemmap[self.showitems[-1]]['sep'].set_visible(False)
        self.get_sep(0).set_visible(False)
        self.get_sep(-1).set_visible(False)

    def expand_items(self):
        if not self.has_limit():
            return

        # fix up snipped items
        rest = self.curitems[self.limit - 1:-1]

        def proc():
            # insert snipped csinfo
            for pos, item in enumerate(rest):
                self.insert_csinfo(item, self.limit + pos)
            # remove snip
            self.remove_snip()

            self.showitems = self.curitems[:]
            self.update_seps()
            self.update_status()

        # determine doing it now or later
        if len(rest) < ASYNC_LIMIT:
            proc()
        else:
            self.update_status(updating=True)
            gtklib.idle_add_single_call(proc)

    def reorder_item(self, pos, insert):
        """
        pos: Number, the position of item to move. This must be curitems
             index, not showitems index.
        insert: Number, the new position to insert target item.
                If list length, indicates the end of the list.
                This must be curitems index, not showitems index.
        """
        # reject unneeded reordering
        if pos == insert or pos + 1 == insert:
            return

        # reorder target csinfo
        if self.has_limit() and self.limit - 1 <= pos:
            item = self.curitems[pos]
            if insert < self.limit - 1:
                # move target csinfo to insert pos
                target = self.itemmap[item]['widget']
                self.csbox.reorder_child(target, insert)

                # remove csinfo to be snipped
                item = self.showitems[-2]
                self.remove_csinfo(item)
            else:
                # remove target csinfo
                self.remove_csinfo(item)

            # insert csinfo the end of the item list
            item = self.curitems[-2]
            self.insert_csinfo(item, -1)

        elif self.has_limit() and self.limit - 1 < insert:
            if self.trans_to_show(insert) < self.limit:
                # remove target csinfo
                rm_item = self.curitems[pos]
            else:
                # move target csinfo to the end of VBox
                item = self.curitems[pos]
                target = self.itemmap[item]['widget']
                numc = len(self.csbox.get_children())
                self.csbox.reorder_child(target, numc - 2)

                # remove last csinfo
                rm_item = self.showitems[-1]

            # remove it
            self.remove_csinfo(rm_item)

            # insert csinfo before snip box
            item = self.curitems[self.limit - 1]
            self.insert_csinfo(item, self.limit - 1)
        else:
            info = self.itemmap[self.showitems[pos]]['widget']
            if insert < pos:
                self.csbox.reorder_child(info, insert)
            else:
                self.csbox.reorder_child(info, insert - 1)

        # reorder curitems
        item = self.curitems[pos]
        items = self.curitems[:pos] + self.curitems[pos+1:]
        if insert < pos:
            items.insert(insert, item)
        else:
            items.insert(insert - 1, item)
        self.curitems = items

        # reorder showitems
        if self.has_limit():
            self.showitems = items[:self.limit-1] + [items[-1]]
        else:
            self.showitems = items

        # show/hide separators
        self.update_seps()

        # just emit 'list-updated' signal
        self.update_status()

    def trans_to_show(self, index):
        """ Translate from curitems index to showitems index """
        numrest = len(self.curitems) - self.limit
        if self.has_limit() and numrest <= index:
            return index - numrest
        return index

    def trans_to_cur(self, index):
        """ Translate from showitems index to curitems index """
        if self.has_limit() and self.limit - 1 <= index:
            return index + len(self.curitems) - self.limit
        return index

    def create_sep(self):
        return FixedHSeparator()

    def add_csinfo(self, item):
        self.insert_csinfo(item, -1)

    def insert_csinfo(self, item, pos):
        """
        item: String, revision number or patch file path to display.
        pos: Number, an index of insertion point.  If -1, indicates
        the end of the item list.
        """
        # create csinfo
        wrapbox = gtk.VBox()
        sep = self.create_sep()
        wrapbox.pack_start(sep, False, False)
        style = self.get_compact_view() and self.lstyle or self.pstyle
        if self.dnd_enable:
            style['selectable'] = False
        info = self.curfactory(item, style)
        if self.sel_enable:
            check = gtk.CheckButton()
            check.set_active(self.chkmap[item])
            check.connect('toggled', self.check_toggled, item)
            align = gtk.Alignment(0.5, 0)
            align.add(check)
            hbox = gtk.HBox()
            hbox.pack_start(align, False, False)
            hbox.pack_start(info, False, False)
            info = hbox
        wrapbox.pack_start(info, False, False)
        wrapbox.show_all()
        self.csbox.pack_start(wrapbox, False, False)
        self.itemmap[item] = {'widget': wrapbox,
                              'info': info,
                              'sep': sep}

        # reorder it
        children = self.csbox.get_children()
        if 1 < len(children) and isinstance(children[-2], FixedHSeparator):
            if pos == -1:
                numc = len(children)
                pos = numc - 2
            elif self.has_limit():
                pos = pos - 1
            self.csbox.reorder_child(wrapbox, pos)

    def remove_csinfo(self, item):
        info = self.itemmap[item]['widget']
        self.csbox.remove(info)
        del self.itemmap[item]

    def add_snip(self):
        wrapbox = gtk.VBox()
        sep = self.create_sep()
        wrapbox.pack_start(sep, False, False)
        snipbox = gtk.HBox()
        wrapbox.pack_start(snipbox, False, False)
        spacer = gtk.Label()
        snipbox.pack_start(spacer, False, False)
        spacer.set_width_chars(24)
        sniplbl = gtk.Label()
        snipbox.pack_start(sniplbl, False, False)
        sniplbl.set_markup('<span size="large" weight="heavy"'
                           ' font_family="monospace">...</span>')
        sniplbl.set_angle(90)
        snipbox.pack_start(gtk.Label())
        self.csbox.pack_start(wrapbox, False, False, 2)
        self.itemmap['snip'] = {'widget': wrapbox,
                                'snip': snipbox,
                                'sep': sep}

    def remove_snip(self):
        if not self.has_limit():
            return
        snip = self.itemmap['snip']['widget']
        self.csbox.remove(snip)
        del self.itemmap['snip']

    ### signal handlers ###

    def check_toggled(self, button, item):
        self.chkmap[item] = button.get_active()
        self.update_status()

    def allbtn_clicked(self, button):
        self.update(self.curitems, self.currepo, limit=False,
                    queue=False, keep=True)

    ### dnd signal handlers ###

    def dnd_begin(self, widget, context):
        self.setup_dnd()
        context.set_icon_pixbuf(self.dnd_pb, 0, 0)

    def dnd_end(self, widget, context):
        self.teardown_dnd()

    def dnd_motion(self, widget, context, x, y, event_time):
        if hasattr(self, 'item_drag') and self.item_drag is not None:
            num = len(self.curitems)
            if not self.hlsep:
                self.setup_dnd(restart=True)
            # highlight separator
            sep = self.get_sep_by_y(y)
            first = self.get_sep(0)
            first.set_visible(first == sep)
            last = self.get_sep(-1)
            last.set_visible(last == sep)
            if self.hlsep != sep:
                if self.hlsep:
                    self.hlsep.drag_unhighlight()
                sep.drag_highlight()
                self.hlsep = sep

    def dnd_leave(self, widget, context, event_time):
        self.teardown_dnd(pause=True)

    def dnd_received(self, widget, context, x, y, sel, target_type, *args):
        if target_type == CSL_DND_ITEM:
            items = self.curitems
            pos, start, end = self.get_item_pos(y, detail=True)
            self.reorder_item(self.item_drag, end)
        elif target_type == CSL_DND_URI_LIST:
            paths = gtklib.normalize_dnd_paths(sel.data)
            if paths:
                self.emit('files-dropped', paths, sel.data)

    def dnd_get(self, widget, context, sel, target_type, event_time):
        pos = self.item_drag
        if target_type == CSL_DND_ITEM and pos is not None:
            sel.set(sel.target, 8, str(self.curitems[pos]))

    def button_press(self, widget, event):
        if not self.curitems:
            return
        # gather geometry data
        items = self.showitems
        if self.has_limit():
            items.append('snip')
        for item in items:
            data = self.itemmap[item]
            alloc = data['widget'].allocation
            data.update(y=alloc.y, height=alloc.height)
            data['bottom'] = alloc.y + alloc.height
        # get pressed csinfo widget based on pointer position
        pos = self.get_item_pos(event.y)
        if pos is None:
            return
        # emit activated signal
        if self.act_enable and event.type == gtk.gdk._2BUTTON_PRESS:
            item = self.curitems[pos]
            self.emit('item-activated', item, self.itemmap[item]['widget'])
        # dnd setup
        if self.dnd_enable and event.type == gtk.gdk.BUTTON_PRESS \
                           and 1 < len(self.curitems):
            # prepare for dnd auto-scrolling
            W = 20
            alloc = self.scroll.child.allocation
            self.areas = {}
            def add(name, arg):
                region = gtk.gdk.region_rectangle(arg)
                self.areas[name] = (region, gtk.gdk.Rectangle(*arg))
            add('top', (0, 0, alloc.width, W))
            add('right', (alloc.width - W, 0, W, alloc.height))
            add('bottom', (0, alloc.height - W, alloc.width, W))
            add('left', (0, 0, W, alloc.height))
            add('center', (W, W, alloc.width - 2 * W, alloc.height - 2 * W))
            # start dnd
            self.item_drag = pos
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
