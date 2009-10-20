# changeset.py - Changeset dialog for TortoiseHg
#
# Copyright 2008 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import gtk
import gobject
import pango
import Queue
import binascii

from mercurial import cmdutil, util, patch, mdiff

from tortoisehg.util.i18n import _
from tortoisehg.util import shlib, hglib

from tortoisehg.hgtk import csinfo, gdialog, gtklib, hgcmd, statusbar

class ChangeSet(gdialog.GDialog):
    'GTK+ based dialog for displaying repository logs'
    def __init__(self, ui, repo, cwd, pats, opts, stbar=None):
        gdialog.GDialog.__init__(self, ui, repo, cwd, pats, opts)
        self.stbar = stbar
        self.glog_parent = None
        self.bfile = None
        self.nothing_loaded = True

    def get_title(self):
        title = _('%s changeset ') % self.get_reponame()
        rev = self.opts['rev']
        if isinstance(rev, str):
            title += rev
        else:
            title += rev[0]
        return title

    def get_icon(self):
        return 'menushowchanged.ico'

    def get_tbbuttons(self):
        return []

    def parent_toggled(self, button):
        self.load_details(self.currev)

    def prepare_display(self):
        self.currow = None
        self.graphview = None
        self.glog_parent = NoneY
        node0, node1 = cmdutil.revpair(self.repo, self.opts.get('rev'))
        self.load_details(self.repo.changelog.rev(node0))

    def save_settings(self):
        settings = gdialog.GDialog.save_settings(self)
        settings['changeset'] = self._hpaned.get_position()
        return settings

    def load_settings(self, settings):
        gdialog.GDialog.load_settings(self, settings)
        if settings and 'changeset' in settings:
            self._setting_hpos = settings['changeset']
        else:
            self._setting_hpos = -1

    def set_repo(self, repo):
        self.repo = repo
        self.summarypanel.update(repo=repo)

    def diff_other_parent(self):
        return self.other_parent_checkbutton.get_active()

    def load_details(self, rev):
        'Load selected changeset details into buffer and filelist'
        self.currev = rev
        ctx = self.repo[rev]
        if not ctx:
            return

        if self.nothing_loaded:
            self.other_parent_box.pack_start(
                self.other_parent_checkbutton, False, False)
            self.nothing_loaded = False

        parents = ctx.parents()
        title = self.get_title()
        if len(parents) == 2:
            self.other_parent_box.show_all()
            if self.diff_other_parent():
                title += ':' + str(parents[1].rev())
            else:
                title += ':' + str(parents[0].rev())
        else:
            self.other_parent_box.hide_all()
            if self.other_parent_checkbutton.get_active():
                # Parent button must be pushed out, but this
                # will cause load_details to be called again
                # so we exit out to prevent recursion.
                self.other_parent_checkbutton.set_active(False)
                return

        if self.clipboard:
            self.clipboard.set_text(str(ctx))

        self.set_title(title)
        if self.diff_other_parent():
            parent = parents[1].node()
        elif parents:
            parent = parents[0].node()
        else:
            parent = self.repo[-1]

        pats = self.pats
        if self.graphview:
            (path, focus) = self.graphview.treeview.get_cursor()
            if path:
                wfile = self.graphview.get_wfile_at_path(path)
                if wfile:
                    pats.append(wfile)

        self._filelist.clear()
        self._filelist.append(('*', _('[All Files]'), ''))
        modified, added, removed = self.repo.status(parent, ctx.node())[:3]
        selrow = None
        for f in modified:
            if f in pats:
                selrow = len(self._filelist)
            self._filelist.append(('M', hglib.toutf(f), f))
        for f in added:
            if f in pats:
                selrow = len(self._filelist)
            self._filelist.append(('A', hglib.toutf(f), f))
        for f in removed:
            if f in pats:
                selrow = len(self._filelist)
            self._filelist.append(('R', hglib.toutf(f), f))
        self.curnodes = (parent, ctx.node())
        if selrow is not None:
            self._filesel.select_path((selrow,))
        elif len(self._filelist) > 1:
            self._filesel.select_path((1,))
        else:
            self._filesel.select_path((0,))

    def load_patch_details(self, patchfile):
        'Load specified patch details into buffer and file list'
        self._filelist.clear()
        self._filelist.append(('*', _('[All Files]'), ''))

        # append files & collect hunks
        self.currev = -1
        self.curphunks = {}
        self.curpatch = patchfile
        pf = open(self.curpatch)
        def get_path(a, b):
            type = (a == '/dev/null') and 'A' or 'M'
            type = (b == '/dev/null') and 'R' or type
            rawpath = (b != '/dev/null') and b or a
            if not (rawpath.startswith('a/') or rawpath.startswith('b/')):
                return type, rawpath
            return type, rawpath.split('/', 1)[-1]
        hunks = []
        files = []
        map = {'MODIFY': 'M', 'ADD': 'A', 'DELETE': 'R',
               'RENAME': '', 'COPY': ''}
        try:
            try:
                for state, values in patch.iterhunks(self.ui, pf):
                    if state == 'git':
                        for m in values:
                            f = m.path
                            self._filelist.append((map[m.op], hglib.toutf(f), f))
                            files.append(f)
                    elif state == 'file':
                        type, path = get_path(values[0], values[1])
                        self.curphunks[path] = hunks = ['diff']
                        if path not in files:
                            self._filelist.append((type, hglib.toutf(path), path))
                            files.append(path)
                    elif state == 'hunk':
                        hunks.extend([l.rstrip('\r\n') for l in values.hunk])
                    else:
                        raise _('unknown hunk type: %s') % state
            except patch.NoHunks:
                pass
        finally:
            pf.close()

        # select first file
        if len(self._filelist) > 1:
            self._filesel.select_path((1,))
        else:
            self._filesel.select_path((0,))

    def filelist_rowchanged(self, sel):
        model, path = sel.get_selected()
        if not path:
            return
        status, file_utf8, file = model[path]
        if self.currev != -1:
            self.curfile = file
            self.generate_change_header()
            if self.curfile:
                self.append_diff(self.curfile)
            else:
                for _, _, f in model:
                    self.append_diff(f)
        else:
            self.generate_patch_header()
            if file:
                self.append_patch_diff(file)
            else:
                self.append_all_patch_diffs()

    def generate_change_header(self):
        self.summarypanel.update(self.currev, self.csetstyle)

        desc = self.summarypanel.get_data('desc')
        self.set_commitlog(desc)

    def generate_patch_header(self):
        self.summarypanel.update(self.curpatch, self.patchstyle)

        desc = self.summarypanel.get_data('desc')
        self.set_commitlog(desc)

    def set_commitlog(self, desc):
        'Append commit log after clearing buffer'
        buf = self._buffer
        buf.set_text('')
        eob = buf.get_end_iter()
        buf.insert(eob, desc + '\n\n')

    def append_diff(self, wfile):
        if not wfile:
            return
        buf, rev = self._buffer, self.currev
        n1, n2 = self.curnodes

        eob = buf.get_end_iter()
        offset = eob.get_offset()

        try:
            fctx = self.repo[rev].filectx(wfile)
        except LookupError:
            fctx = None
        if fctx and fctx.size() > hglib.getmaxdiffsize(self.ui):
            lines = ['diff',
                    _(' %s is larger than the specified max diff size') % wfile]
        else:
            lines = []
            m = cmdutil.matchfiles(self.repo, [wfile])
            opts = mdiff.diffopts(git=True, nodates=True)
            try:
                for s in patch.diff(self.repo, n1, n2, match=m, opts=opts):
                    lines.extend(s.splitlines())
            except (RepoLookupError, RepoError, LookupError), e:
                err = _('Repository Error:  %s, refresh suggested') % str(e)
                lines = ['diff', '', err]
        tags, lines = self.prepare_diff(lines, offset, wfile)
        for l in lines:
            buf.insert(eob, l)

        # inserts the tags
        for name, p0, p1 in tags:
            i0 = buf.get_iter_at_offset(p0)
            i1 = buf.get_iter_at_offset(p1)
            buf.apply_tag_by_name(name, i0, i1)

        sob, eob = buf.get_bounds()
        pos = buf.get_iter_at_offset(offset)
        buf.apply_tag_by_name('mono', pos, eob)
        return True

    def append_patch_diff(self, patchfile):
        if not patchfile:
            return

        # append diffs
        buf = self._buffer
        eob = buf.get_end_iter()
        offset = eob.get_offset()
        lines = self.curphunks[patchfile]
        tags, lines = self.prepare_diff(lines, offset, patchfile)
        for line in lines:
            buf.insert(eob, line)

        # insert the tags
        for name, p0, p1 in tags:
            i0 = buf.get_iter_at_offset(p0)
            i1 = buf.get_iter_at_offset(p1)
            buf.apply_tag_by_name(name, i0, i1)

        sob, eob = buf.get_bounds()
        pos = buf.get_iter_at_offset(offset)
        buf.apply_tag_by_name('mono', pos, eob)

    def append_all_patch_diffs(self):
        model = self._filelist
        if len(model) > 1:
            for st, fu, fn in model:
                self.append_patch_diff(fn)
        else:
            self._buffer.insert(self._buffer.get_end_iter(),
                                '\n' + _('[no hunks to display]'))

    def prepare_diff(self, difflines, offset, fname):
        'Borrowed from hgview; parses changeset diffs'
        def addtag( name, offset, length ):
            if tags and tags[-1][0] == name and tags[-1][2]==offset:
                tags[-1][2] += length
            else:
                tags.append( [name, offset, offset+length] )

        add, rem = 0, 0
        for l in difflines[1:]:
            if l.startswith('+'):
                add += 1
            elif l.startswith('-'):
                rem += 1
        outlines = []
        tags = []
        txt = hglib.toutf('=== (+%d,-%d) %s ===\n' % (add, rem, fname))
        addtag( 'greybg', offset, len(txt) )
        outlines.append(txt)
        offset += len(txt.decode('utf-8'))
        for l1 in difflines[1:]:
            l = hglib.toutf(l1)
            if l.startswith('+++'):
                continue
            if l.startswith('---'):
                continue
            if l.startswith('@@'):
                tag = 'blue'
            elif l.startswith('+'):
                tag = 'green'
                l = hglib.diffexpand(l)
            elif l.startswith('-'):
                tag = 'red'
                l = hglib.diffexpand(l)
            else:
                tag = 'black'
                l = hglib.diffexpand(l)
            l = l+"\n"
            length = len(l.decode('utf-8'))
            addtag( tag, offset, length )
            outlines.append( l )
            offset += length
        return tags, outlines

    def link_event(self, tag, widget, event, liter):
        if event.type != gtk.gdk.BUTTON_RELEASE:
            return
        text = self.get_link_text(tag, widget, liter)
        if not text:
            return
        linkrev = long(text.split(' ')[0])
        if self.graphview:
            self.graphview.set_revision_id(linkrev, load=True)
        else:
            self.load_details(linkrev)

    def get_link_text(self, tag, widget, liter):
        'handle clicking on a link in a textview'
        text_buffer = widget.get_buffer()
        beg = liter.copy()
        while not beg.begins_tag(tag):
            beg.backward_char()
        end = liter.copy()
        while not end.ends_tag(tag):
            end.forward_char()
        text = text_buffer.get_text(beg, end)
        return text

    def file_context_menu(self):
        def create_menu(label, callback):
            menuitem = gtk.MenuItem(label, True)
            menuitem.connect('activate', callback)
            menuitem.set_border_width(1)
            return menuitem

        menu = gtklib.MenuItems()
        menu.append(create_menu(_('_Visual Diff'), self.diff_file_rev))
        menu.append(create_menu(_('Diff to _local'), self.diff_to_local))
        menu.append_sep()
        menu.append(create_menu(_('_View at Revision'), self.view_file_rev))
        self.save_menu = create_menu(_('_Save at Revision...'),
            self.save_file_rev)
        menu.append(self.save_menu)
        menu.append_sep()
        menu.append(create_menu(_('_File History'), self.file_history))
        self.ann_menu = create_menu(_('_Annotate File'), self.ann_file)
        menu.append(self.ann_menu)
        menu.append_sep()
        menu.append(create_menu(_('_Revert File Contents'), self.revert_file))

        menu = menu.create_menu()
        menu.show_all()
        return menu

    def get_body(self):
        self.curfile = ''
        if self.repo.ui.configbool('tortoisehg', 'copyhash'):
            sel = (os.name == 'nt') and 'CLIPBOARD' or 'PRIMARY'
            self.clipboard = gtk.Clipboard(selection=sel)
        else:
            self.clipboard = None
        self.filemenu = self.file_context_menu()

        # changeset frame
        details_frame = gtk.Frame()
        details_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        details_frame.add(scroller)

        details_box = gtk.VBox()
        scroller.add_with_viewport(details_box)
        scroller.child.set_shadow_type(gtk.SHADOW_NONE)

        ## changeset panel
        def data_func(widget, item, ctx):
            def summary_line(desc):
                desc = desc.replace('\0', '')
                return hglib.toutf(desc.split('\n')[0][:80])
            def revline_data(ctx):
                if isinstance(ctx, basestring):
                    return ctx
                desc = ctx.description()
                return (str(ctx.rev()), str(ctx), summary_line(desc))
            if item == 'cset':
                return revline_data(ctx)
            elif item == 'branch':
                value = hglib.toutf(ctx.branch())
                return value != 'default' and value or None
            if item == 'dateage':
                date = widget.get_data('date')
                age = widget.get_data('age')
                return (date, age)
            elif item == 'parents':
                return [revline_data(ctx) for ctx in ctx.parents()]
            elif item == 'children':
                return [revline_data(ctx) for ctx in ctx.children()]
            elif item == 'transplant':
                extra = ctx.extra()
                try:
                    ts = extra['transplant_source']
                    try:
                        tctx = self.repo[ts]
                        return revline_data(tctx)
                    except (LookupError, RepoLookupError, RepoError):
                        return binascii.hexlify(ts)
                except KeyError:
                    return None
            elif item == 'patch':
                if hasattr(ctx, '_patchname'):
                    desc = ctx.description()
                    return (ctx._patchname, str(ctx), summary_line(desc))
                return None
            raise csinfo.UnknownItem(item)
        def label_func(widget, item):
            if item == 'cset':
                return _('Changeset:')
            elif item == 'dateage':
                return _('Date:')
            elif item == 'parents':
                return _('Parent:')
            elif item == 'children':
                return _('Child:')
            elif item == 'transplant':
                return _('Transplant:')
            elif item == 'patch':
                return _('Patch:')
            raise csinfo.UnknownItem(item)
        def markup_func(widget, item, value):
            def revid_markup(revid):
                return gtklib.markup(revid, face='monospace', size='9000')
            def revline_markup(revnum, revid, summary):
                revnum = gtklib.markup(revnum)
                summary = gtklib.markup(summary)
                if revid:
                    revid = revid_markup(revid)
                    return '%s (%s) %s' % (revnum, revid, summary)
                else:
                    return '%s - %s' % (revnum, summary)
            if item in ('cset', 'transplant', 'patch'):
                if isinstance(value, basestring):
                    return revid_markup(value)
                return revline_markup(*value)
            elif item in ('parents', 'children'):
                csets = []
                for cset in value:
                    if isinstance(cset, basestring):
                        csets.append(revid_markup(cset))
                    else:
                        csets.append(revline_markup(*cset))
                return csets
            elif item == 'dateage':
                return gtklib.markup('%s (%s)' % value)
            raise csinfo.UnknownItem(item)

        custom = csinfo.custom(data=data_func, label=label_func,
                               markup=markup_func)
        self.csetstyle = csinfo.panelstyle(contents=('cset', 'branch',
                                'user', 'dateage', 'parents', 'children',
                                'tags', 'transplant'), selectable=True)
        self.patchstyle = csinfo.panelstyle(contents=('patch', 'branch',
                                 'user', 'dateage', 'parents'),
                                 selectable=True)
        self.summarypanel = csinfo.create(self.repo, custom=custom)
        details_box.pack_start(self.summarypanel, False, False)
        details_box.pack_start(gtk.HSeparator(), False, False)

        ## changeset diff
        details_text = gtk.TextView()
        details_text.set_wrap_mode(gtk.WRAP_NONE)
        details_text.connect('populate-popup', self.add_to_popup)
        details_text.set_editable(False)
        details_text.modify_font(pango.FontDescription(self.fontcomment))
        details_box.pack_start(details_text)

        self._buffer = gtk.TextBuffer()
        self.setup_tags()
        details_text.set_buffer(self._buffer)
        self.textview = details_text

        ## file list
        filelist_tree = gtk.TreeView()
        filesel = filelist_tree.get_selection()
        filesel.connect('changed', self.filelist_rowchanged)
        self._filesel = filesel
        filelist_tree.connect('button-release-event',
                self.file_button_release)
        filelist_tree.connect('popup-menu', self.file_popup_menu)
        filelist_tree.connect('row-activated', self.file_row_act)
        filelist_tree.set_search_equal_func(self.search_filelist)
        filelist_tree.modify_font(pango.FontDescription(self.fontlist))

        accelgroup = gtk.AccelGroup()
        if self.glog_parent:
            self.glog_parent.add_accel_group(accelgroup)
        else:
            self.add_accel_group(accelgroup)
        mod = gtklib.get_thg_modifier()
        key, modifier = gtk.accelerator_parse(mod+'d')
        filelist_tree.add_accelerator('thg-diff', accelgroup, key,
                        modifier, gtk.ACCEL_VISIBLE)
        filelist_tree.connect('thg-diff', self.thgdiff)

        self._filelist = gtk.ListStore(
                gobject.TYPE_STRING,   # MAR status
                gobject.TYPE_STRING,   # filename (utf-8 encoded)
                gobject.TYPE_STRING,   # filename
                )
        filelist_tree.set_model(self._filelist)
        column = gtk.TreeViewColumn(_('Stat'), gtk.CellRendererText(), text=0)
        filelist_tree.append_column(column)
        column = gtk.TreeViewColumn(_('Files'), gtk.CellRendererText(), text=1)
        filelist_tree.append_column(column)

        list_frame = gtk.Frame()
        list_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(filelist_tree)
        flbox = gtk.VBox()
        flbox.pack_start(scroller)
        list_frame.add(flbox)

        self.other_parent_box = gtk.HBox()
        flbox.pack_start(self.other_parent_box, False, False)

        btn = gtk.CheckButton(_('Diff to second Parent'))
        btn.connect('toggled', self.parent_toggled)
        # don't pack btn yet to keep it initially invisible
        self.other_parent_checkbutton = btn

        self._hpaned = gtk.HPaned()
        self._hpaned.pack1(list_frame, True, True)
        self._hpaned.pack2(details_frame, True, True)
        self._hpaned.set_position(self._setting_hpos)

        if self.stbar:
            # embedded by changelog browser
            return self._hpaned
        else:
            # add status bar for main app
            vbox = gtk.VBox()
            vbox.pack_start(self._hpaned, True, True)
            self.stbar = statusbar.StatusBar()
            self.stbar.show()
            vbox.pack_start(gtk.HSeparator(), False, False)
            vbox.pack_start(self.stbar, False, False)
            return vbox

    def search_filelist(self, model, column, key, iter):
        'case insensitive filename search'
        key = key.lower()
        if key in model.get_value(iter, 1).lower():
            return False
        return True

    def setup_tags(self):
        'Creates the tags to be used inside the TextView'
        def make_texttag( name, **kwargs ):
            'Helper function generating a TextTag'
            tag = gtk.TextTag(name)
            for key, value in kwargs.iteritems():
                key = key.replace("_","-")
                try:
                    tag.set_property( key, value )
                except TypeError:
                    print "Warning the property %s is unsupported in" % key
                    print "this version of pygtk"
            return tag

        tag_table = self._buffer.get_tag_table()

        tag_table.add(make_texttag('changeset', foreground='#000090',
                paragraph_background='#F0F0F0'))
        tag_table.add(make_texttag('changeset-summary', foreground='black',
                paragraph_background='#F0F0F0', family='Sans'))
        tag_table.add(make_texttag('date', foreground='#000090',
                paragraph_background='#F0F0F0'))
        tag_table.add(make_texttag('tag', foreground='#000090',
                paragraph_background='#F0F0F0'))
        tag_table.add(make_texttag('files', foreground='#5C5C5C',
                paragraph_background='#F0F0F0'))
        tag_table.add(make_texttag('parent', foreground='#000090',
                paragraph_background='#F0F0F0'))
        tag_table.add(make_texttag('parenthl', foreground='#000090',
                paragraph_background='#F0F0F0',
                weight=pango.WEIGHT_BOLD ))

        tag_table.add( make_texttag( 'mono', family='Monospace' ))
        tag_table.add( make_texttag( 'blue', foreground='blue' ))
        tag_table.add( make_texttag( 'red', foreground='red' ))
        tag_table.add( make_texttag( 'green', foreground='darkgreen' ))
        tag_table.add( make_texttag( 'black', foreground='black' ))
        tag_table.add( make_texttag( 'greybg',
                                     paragraph_background='grey',
                                     weight=pango.WEIGHT_BOLD ))
        tag_table.add( make_texttag( 'yellowbg', background='yellow' ))
        link_tag = make_texttag( 'link', foreground='blue',
                                 underline=pango.UNDERLINE_SINGLE )
        linkhl_tag = make_texttag( 'linkhl', foreground='blue',
                                 underline=pango.UNDERLINE_SINGLE,
                                weight=pango.WEIGHT_BOLD )
        link_tag.connect('event', self.link_event )
        linkhl_tag.connect('event', self.link_event )
        tag_table.add( link_tag )
        tag_table.add( linkhl_tag )

    def file_button_release(self, widget, event):
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK |
            gtk.gdk.CONTROL_MASK)):
            self.file_popup_menu(widget, event.button, event.time)
        return False

    def file_popup_menu(self, treeview, button=0, time=0):
        if not self.curfile:
            return
        self.filemenu.popup(None, None, None, button, time)

        # If the filelog entry this changeset references does not link
        # back to this changeset, it means this changeset did not
        # actually change the contents of this file, and thus the file
        # cannot be annotated at this revision (since this changeset
        # does not appear in the filelog)
        ctx = self.repo[self.currev]
        try:
            fctx = ctx.filectx(self.curfile)
            has_filelog = fctx.filelog().linkrev(fctx.filerev()) == ctx.rev()
        except LookupError:
            has_filelog = False
        self.ann_menu.set_sensitive(has_filelog)
        self.save_menu.set_sensitive(has_filelog)
        return True

    def thgdiff(self, treeview):
        # Do not steal ctrl-d from changelog treeview
        if not treeview.is_focus() and self.glog_parent:
            w = self.glog_parent.get_focus()
            if isinstance(w, gtk.TreeView):
                w.emit('thg-diff')
            return False
        if not self.curfile:
            return False
        opts = {'change':str(self.currev), 'bundle':self.bfile}
        self._do_diff([self.curfile], opts)

    def file_row_act(self, tree, path, column) :
        'Default action is the first entry in the context menu'
        self.filemenu.get_children()[0].activate()
        return True

    def save_file_rev(self, menuitem):
        wfile = util.localpath(self.curfile)
        wfile, ext = os.path.splitext(os.path.basename(wfile))
        if wfile:
            filename = "%s@%d%s" % (wfile, self.currev, ext)
        else:
            filename = "%s@%d" % (ext, self.currev)
        result = gtklib.NativeSaveFileDialogWrapper(title=_("Save file to"),
                                                    initial=self.cwd,
                                                    filename=filename).run()
        if result:
            if os.path.exists(result):
                res = gdialog.Confirm(_('Confirm Overwrite'), [], self,
                   _('The file "%s" already exists!\n\n'
                     'Do you want to overwrite it?') % result).run()
                if res != gtk.RESPONSE_YES:
                    return
                os.remove(result)

            q = Queue.Queue()
            hglib.hgcmd_toq(q, 'cat', '--rev',
                str(self.currev), '--output', hglib.fromutf(result), self.curfile)

    def diff_to_local(self, menuitem):
        if not self.curfile:
            return
        opts = {'rev':[str(self.currev)], 'bundle':self.bfile}
        self._do_diff([self.curfile], opts)

    def diff_file_rev(self, menuitem):
        'User selected visual diff file from the file list context menu'
        if not self.curfile:
            return

        rev = self.currev
        opts = {'change':str(rev), 'bundle':self.bfile}
        parents = self.repo[rev].parents()
        if len(parents) == 2:
            if self.diff_other_parent():
                parent = parents[1].rev()
            else:
                parent = parents[0].rev()
            opts['rev'] = [str(parent), str(rev)]

        self._do_diff([self.curfile], opts)

    def view_file_rev(self, menuitem):
        'User selected view file revision from the file list context menu'
        if not self.curfile:
            return
        rev = self.currev
        parents = [x.rev() for x in self.repo[rev].parents()]
        if len(parents) == 0:
            parent = rev-1
        else:
            parent = parents[0]
        pair = '%u:%u' % (parent, rev)
        self._node1, self._node2 = cmdutil.revpair(self.repo, [pair])
        self._view_files([self.curfile], False)

    def ann_file(self, menuitem):
        'User selected annotate file from the file list context menu'
        from tortoisehg.hgtk import datamine
        rev = self.currev
        dialog = datamine.DataMineDialog(self.ui, self.repo, self.cwd, [], {})
        dialog.display()
        dialog.close_current_page()
        dialog.add_annotate_page(self.curfile, str(rev))

    def file_history(self, menuitem):
        'User selected file history from file list context menu'
        if self.glog_parent:
            # If this changeset browser is embedded in glog, send
            # send this event to the main app
            opts = {'pats' : [self.curfile]}
            self.glog_parent.filtercombo.set_active(1)
            self.glog_parent.filterentry.set_text(self.curfile)
            self.glog_parent.custombutton.set_active(True)
            self.glog_parent.filter = 'custom'
            self.glog_parent.reload_log(**opts)
        else:
            # Else launch our own glog instance
            from tortoisehg.hgtk import history
            dlg = history.run(self.ui, filehist=self.curfile)
            dlg.display()

    def revert_file(self, menuitem):
        'User selected file revert from the file list context menu'
        rev = self.currev
        dialog = gdialog.Confirm(_('Confirm revert file to old revision'),
                 [], self, _('Revert %s to contents at revision %d?') %
                 (self.curfile, rev))
        if dialog.run() == gtk.RESPONSE_NO:
            return
        cmdline = ['hg', 'revert', '--verbose', '--rev', str(rev), self.curfile]
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.run()
        dlg.hide()
        shlib.shell_notify([self.repo.wjoin(self.curfile)])

    def add_to_popup(self, textview, menu):
        menu_items = (('----', None),
                      (_('Toggle _Wordwrap'), self.toggle_wordwrap),
                     )
        for label, handler in menu_items:
            if label == '----':
                menuitem = gtk.SeparatorMenuItem()
            else:
                menuitem = gtk.MenuItem(label)
            if handler:
                menuitem.connect('activate', handler)
            menu.append(menuitem)
        menu.show_all()

    def toggle_wordwrap(self, sender):
        if self.textview.get_wrap_mode() != gtk.WRAP_NONE:
            self.textview.set_wrap_mode(gtk.WRAP_NONE)
        else:
            self.textview.set_wrap_mode(gtk.WRAP_WORD)
