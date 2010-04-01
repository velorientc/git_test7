# changeset.py - Changeset dialog for TortoiseHg
#
# Copyright 2008 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import re
import gtk
import gobject
import pango
import Queue

from mercurial import cmdutil, util, patch, mdiff, error

from tortoisehg.util.i18n import _
from tortoisehg.util import shlib, hglib, paths

from tortoisehg.hgtk import csinfo, gdialog, gtklib, hgcmd, statusbar

class ChangeSet(gdialog.GWindow):
    'GTK+ based dialog for displaying repository logs'
    def __init__(self, ui, repo, cwd, pats, opts, stbar=None):
        gdialog.GWindow.__init__(self, ui, repo, cwd, pats, opts)
        self.stbar = stbar
        self.glog_parent = None
        self.bfile = None
        self.colorstyle = repo.ui.config('tortoisehg', 'diffcolorstyle')

        # initialize changeset/issue tracker link regex and dict
        csmatch = r'(\b[0-9a-f]{12}(?:[0-9a-f]{28})?\b)'
        httpmatch = r'(\b(http|https)://([-A-Za-z0-9+&@#/%?=~_()|!:,.;]*[-A-Za-z0-9+&@#/%=~_()|]))'
        issue = repo.ui.config('tortoisehg', 'issue.regex')
        if issue:
            regexp = r'%s|%s|(%s)' % (csmatch, httpmatch, issue)
        else:
            regexp = r'%s|%s' % (csmatch, httpmatch)
        self.bodyre = re.compile(regexp)
        self.issuedict = dict()

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
        self.glog_parent = None
        node0, node1 = cmdutil.revpair(self.repo, self.opts.get('rev'))
        self.load_details(self.repo.changelog.rev(node0))

    def save_settings(self):
        settings = gdialog.GWindow.save_settings(self)
        settings['changeset'] = self._hpaned.get_position()
        return settings

    def load_settings(self, settings):
        gdialog.GWindow.load_settings(self, settings)
        if settings and 'changeset' in settings:
            self._setting_hpos = settings['changeset']
        else:
            self._setting_hpos = -1

    def set_repo(self, repo):
        self.repo = repo
        self.summarypanel.update(repo=repo)

    def clear_cache(self):
        self.summarypanel.info.clear_cache()

    def clear(self):
        self._buffer.set_text('')
        self._filelist.clear()
        self.summarybox.hide()

    def diff_other_parent(self):
        return self.parent_button.get_active()

    def load_details(self, rev):
        'Load selected changeset details into buffer and filelist'
        oldrev = hasattr(self, 'currev') and self.currev or None
        self.currev = rev
        ctx = self.repo[rev]
        if not ctx:
            return

        parents = ctx.parents()
        title = self.get_title()
        if parents:
            if len(parents) == 2:
                # deferred adding of parent check button
                if not self.parent_button.parent:
                    self.parent_box.pack_start(self.parent_button, False, False)
                    self.parent_box.pack_start(gtk.HSeparator(), False, False)
                    self.parent_box.show_all()

                # show parent box
                self.parent_box.show()

                # uncheck the check button
                if rev != oldrev:
                    self.parent_button.handler_block_by_func(
                            self.parent_toggled)
                    self.parent_button.set_active(False)
                    self.parent_button.handler_unblock_by_func(
                            self.parent_toggled)

                # determine title and current parent
                if self.diff_other_parent():
                    title += ':' + str(parents[1].rev())
                    parent = parents[1].node()
                else:
                    title += ':' + str(parents[0].rev())
                    parent = parents[0].node()

                # clear cache for highlighting parent correctly
                self.clear_cache()
            else:
                # hide parent box
                self.parent_box.hide()
                parent = parents[0].node()
        else:
            parent = self.repo[-1]

        oldother = hasattr(self, 'otherparent') and self.otherparent or None
        self.otherparent = len(parents) == 2 and self.diff_other_parent()

        # refresh merge row without graph redrawing
        if self.graphview:
            gview = self.graphview
            if oldother:
                gview.model.clear_parents()
                gview.queue_draw()
            elif self.otherparent:
                gview.model.set_parent(ctx.rev(), parent)
                gview.queue_draw()

        # update dialog title
        self.set_title(title)

        if self.clipboard:
            self.clipboard.set_text(str(ctx))

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
            self._filelist_tree.set_cursor((selrow,))
        elif len(self._filelist) > 1:
            self._filesel.select_path((1,))
            self._filelist_tree.set_cursor((1,))
        else:
            self._filesel.select_path((0,))

        self.reset_scroll_pos()

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

        self.reset_scroll_pos()

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

    def reset_scroll_pos(self):
        adj = self.diffscroller.get_vadjustment()
        adj.set_value(0)
        adj = self.diffscroller.get_hadjustment()
        adj.set_value(0)

    def generate_change_header(self):
        self.summarypanel.update(self.currev, self.csetstyle)
        self.summarybox.show()

        desc = self.summarypanel.get_data('desc')
        self.set_commitlog(desc)

    def generate_patch_header(self):
        self.summarypanel.update(self.curpatch, self.patchstyle)
        self.summarybox.show()

        desc = self.summarypanel.get_data('desc')
        self.set_commitlog(desc)

    def set_commitlog(self, desc):
        'Append commit log after clearing buffer'
        buf = self._buffer
        buf.set_text('')
        eob = buf.get_end_iter()
        desc = desc.rstrip('\n\r')

        pos = 0
        self.issuedict.clear()
        for m in self.bodyre.finditer(desc):
            a, b = m.span()
            if a >= pos:
                buf.insert(eob, desc[pos:a])
                pos = b
            groups = m.groups()
            if groups[0]:
                link = groups[0]
                buf.insert_with_tags_by_name(eob, link, 'csetlink')
            elif groups[1]:
                link = groups[1]
                buf.insert_with_tags_by_name(eob, link, 'urllink')
            else:
                link = groups[4]
                if len(groups) > 4:
                    self.issuedict[link] = groups[4:]
                buf.insert_with_tags_by_name(eob, link, 'issuelink')
        if pos < len(desc):
            buf.insert(eob, desc[pos:])
        buf.insert(eob, '\n\n')

    def append_diff(self, wfile):
        if not wfile:
            return
        buf, rev = self._buffer, self.currev
        n1, n2 = self.curnodes

        eob = buf.get_end_iter()
        offset = eob.get_offset()

        try:
            fctx = self.repo[rev].filectx(wfile)
        except error.LookupError:
            fctx = None
        if fctx and fctx.size() > hglib.getmaxdiffsize(self.repo.ui):
            lines = ['diff',
                    _(' %s is larger than the specified max diff size') % wfile]
        else:
            lines = []
            m = cmdutil.matchfiles(self.repo, [wfile])
            opts = mdiff.diffopts(git=True, nodates=True)
            try:
                for s in patch.diff(self.repo, n1, n2, match=m, opts=opts):
                    lines.extend(s.splitlines())
            except (error.RepoLookupError, error.RepoError, error.LookupError), e:
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
        buf.apply_tag_by_name('diff', pos, eob)
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
        buf.apply_tag_by_name('diff', pos, eob)

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
            if l.startswith('--- '):
                continue
            if l.startswith('+++ '):
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

    def link_event(self, label, event, revnum):
        revnum = int(revnum)
        if self.graphview:
            self.graphview.set_revision_id(revnum, load=True)
        else:
            self.load_details(revnum)

    def file_context_menu(self):
        m = gtklib.MenuBuilder()
        m.append(_('_Visual Diff'), self.diff_file_rev,
                 gtk.STOCK_JUSTIFY_FILL)
        m.append(_('Diff to _local'), self.diff_to_local)
        m.append_sep()
        m.append(_('_View at Revision'), self.view_file_rev, gtk.STOCK_EDIT)
        self.msave = m.append(_('_Save at Revision...'),
                              self.save_file_rev, gtk.STOCK_SAVE)
        m.append_sep()
        m.append(_('_File History'), self.file_history, 'menulog.ico')
        self.ann_menu = m.append(_('_Annotate File'), self.ann_file,
                                 'menublame.ico')
        m.append_sep()
        m.append(_('_Revert File Contents'), self.revert_file,
                 gtk.STOCK_MEDIA_REWIND)

        menu = m.build()
        menu.show_all()
        return menu

    def get_body(self):
        embedded = bool(self.stbar)
        use_expander = embedded and self.ui.configbool(
            'tortoisehg', 'changeset-expander')

        self.curfile = ''
        if self.repo.ui.configbool('tortoisehg', 'copyhash'):
            sel = (os.name == 'nt') and 'CLIPBOARD' or 'PRIMARY'
            self.clipboard = gtk.Clipboard(selection=sel)
        else:
            self.clipboard = None
        self.filemenu = self.file_context_menu()

        details_frame_parent = gtk.VBox()

        # changeset frame
        details_frame = gtk.Frame()
        details_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        details_frame.add(scroller)
        self.diffscroller = scroller

        details_box = gtk.VBox()
        scroller.add_with_viewport(details_box)
        scroller.child.set_shadow_type(gtk.SHADOW_NONE)

        ## changeset panel
        def revid_markup(revid, **kargs):
            opts = dict(face='monospace', size='9000')
            opts.update(kargs)
            return gtklib.markup(revid, **opts)
        def data_func(widget, item, ctx):
            def summary_line(desc):
                desc = hglib.tounicode(desc.replace('\0', '').split('\n')[0])
                return hglib.toutf(desc[:80])
            def revline_data(ctx, hl=False, branch=None):
                if isinstance(ctx, basestring):
                    return ctx
                desc = ctx.description()
                return (str(ctx.rev()), str(ctx), summary_line(desc), hl, branch)
            if item == 'cset':
                return revline_data(ctx)
            elif item == 'branch':
                value = hglib.toutf(ctx.branch())
                return value != 'default' and value or None
            elif item == 'parents':
                pindex = self.diff_other_parent() and 1 or 0
                pctxs = ctx.parents()
                parents = []
                for pctx in pctxs:
                    highlight = len(pctxs) == 2 and pctx == pctxs[pindex]
                    branch = None
                    if hasattr(pctx, 'branch') and pctx.branch() != ctx.branch():
                        branch = pctx.branch()
                    parents.append(revline_data(pctx, highlight, branch))
                return parents
            elif item == 'children':
                children = []
                for cctx in ctx.children():
                    branch = None
                    if hasattr(cctx, 'branch') and cctx.branch() != ctx.branch():
                        branch = cctx.branch()
                    children.append(revline_data(cctx, branch=branch))
                return children
            elif item in ('transplant', 'p4', 'svn'):
                ts = widget.get_data(item, usepreset=True)
                if not ts:
                    return None
                try:
                    tctx = self.repo[ts]
                    return revline_data(tctx)
                except (error.LookupError, error.RepoLookupError, error.RepoError):
                    return ts
            elif item == 'patch':
                if hasattr(ctx, '_patchname'):
                    desc = ctx.description()
                    return (ctx._patchname, str(ctx), summary_line(desc))
                return None
            raise csinfo.UnknownItem(item)
        def label_func(widget, item):
            if item == 'cset':
                return _('Changeset:')
            elif item == 'parents':
                return _('Parent:')
            elif item == 'children':
                return _('Child:')
            elif item == 'patch':
                return _('Patch:')
            raise csinfo.UnknownItem(item)
        def markup_func(widget, item, value):
            def revline_markup(revnum, revid, summary, highlight=None, branch=None):
                revnum = gtklib.markup(revnum)
                summary = gtklib.markup(summary)
                if revid:
                    revid = revid_markup(revid)
                    if branch:
                        return '%s (%s) %s %s' % (revnum, revid, branch, summary)
                    return '%s (%s) %s' % (revnum, revid, summary)
                else:
                    if branch:
                        return '%s - %s %s' % (revnum, branch, summary)
                    return '%s - %s' % (revnum, summary)
            if item in ('cset', 'transplant', 'patch', 'p4', 'svn'):
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
            raise csinfo.UnknownItem(item)
        def widget_func(widget, item, markups):
            def linkwidget(revnum, revid, summary, highlight=None, branch=None):
                # revision label
                opts = dict(underline='single', color='blue')
                if highlight:
                    opts['weight'] = 'bold'
                rev = '%s (%s)' % (gtklib.markup(revnum, **opts),
                        revid_markup(revid, **opts))
                revlabel = gtk.Label()
                revlabel.set_markup(rev)
                revlabel.set_selectable(True)
                revlabel.connect('button-release-event', self.link_event, revnum)
                # summary & branch label
                sum = gtklib.markup(summary)
                if branch:
                    sum = gtklib.markup(branch, color='black',
                        background=gtklib.PGREEN) + ' ' + sum
                sumlabel = gtk.Label()
                sumlabel.set_markup(sum)
                sumlabel.set_selectable(True)
                box = gtk.HBox()
                box.pack_start(revlabel, False, False)
                box.pack_start(sumlabel, True, True, 4)
                return box
            def genwidget(param):
                if isinstance(param, basestring):
                    label = gtk.Label()
                    label.set_markup(param)
                    label.set_selectable(True)
                    return label
                return linkwidget(*param)
            if item in ('parents', 'children'):
                csets = widget.get_data(item)
                return [genwidget(cset) for cset in csets]
            elif item == 'transplant':
                cset = widget.get_data(item)
                return genwidget(cset)
            raise csinfo.UnknownItem(item)

        custom = csinfo.custom(data=data_func, label=label_func,
                               markup=markup_func, widget=widget_func)
        self.csetstyle = csinfo.panelstyle(contents=('cset', 'branch',
                                'user', 'dateage', 'parents', 'children',
                                'tags', 'transplant', 'p4', 'svn'), selectable=True)
        self.patchstyle = csinfo.panelstyle(contents=('patch', 'branch',
                                 'user', 'dateage', 'parents'),
                                 selectable=True)
        if use_expander:
            self.csetstyle['expander'] = True
            self.patchstyle['expander'] = True

        self.summarypanel = csinfo.create(self.repo, custom=custom)

        ## summary box (summarypanel + separator)
        self.summarybox = gtk.VBox()
        if use_expander:
            # don't scroll summarybox
            details_frame_parent.pack_start(self.summarybox, False, False)
        else:
            # scroll summarybox
            details_box.pack_start(self.summarybox, False, False)
        self.summarybox.pack_start(self.summarypanel, False, False)
        self.summarybox.pack_start(gtk.HSeparator(), False, False)

        ## changeset diff
        details_text = gtk.TextView()
        details_text.set_wrap_mode(gtk.WRAP_NONE)
        details_text.connect('populate-popup', self.add_to_popup)
        details_text.set_editable(False)
        details_text.modify_font(self.fonts['comment'])
        details_box.pack_start(details_text)

        self._buffer = gtk.TextBuffer()
        self.setup_tags()
        details_text.set_buffer(self._buffer)
        self.textview = details_text

        ## file list
        filelist_tree = gtk.TreeView()
        filelist_tree.set_headers_visible(False)
        filesel = filelist_tree.get_selection()
        filesel.connect('changed', self.filelist_rowchanged)
        self._filesel = filesel
        filelist_tree.connect('button-release-event',
                self.file_button_release)
        filelist_tree.connect('popup-menu', self.file_popup_menu)
        filelist_tree.connect('row-activated', self.file_row_act)
        filelist_tree.set_search_equal_func(self.search_filelist)
        filelist_tree.modify_font(self.fonts['list'])
        self._filelist_tree = filelist_tree

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

        def scroll_details(widget, direction=gtk.SCROLL_PAGE_DOWN):
            self.diffscroller.emit("scroll-child", direction, False)

        # signal, accelerator key, handler, (parameters,)
        status_accelerators = [
            ('status-scroll-down', 'bracketright', scroll_details,
             (gtk.SCROLL_PAGE_DOWN,)),
            ('status-scroll-up', 'bracketleft', scroll_details,
             (gtk.SCROLL_PAGE_UP,)),
            ('status-next-file', 'period', gtklib.move_treeview_selection,
             (filelist_tree, 1)),
            ('status-previous-file', 'comma', gtklib.move_treeview_selection,
             (filelist_tree, -1)),
        ]
        
        for signal, accelerator, handler, param in status_accelerators:
            root = self.glog_parent or self
            gtklib.add_accelerator(root, signal, accelgroup,
                                   mod + accelerator)
            root.connect(signal, handler, *param)

        self._filelist = gtk.ListStore(
                gobject.TYPE_STRING,   # MAR status
                gobject.TYPE_STRING,   # filename (utf-8 encoded)
                gobject.TYPE_STRING,   # filename
                )
        filelist_tree.set_model(self._filelist)

        column = gtk.TreeViewColumn()
        filelist_tree.append_column(column)

        iconcell = gtk.CellRendererPixbuf()
        filecell = gtk.CellRendererText()

        column.pack_start(iconcell, expand=False)
        column.pack_start(filecell, expand=False)
        column.add_attribute(filecell, 'text', 1)

        size = gtk.ICON_SIZE_SMALL_TOOLBAR
        addedpixbuf = gtklib.get_icon_pixbuf('fileadd.ico', size)
        removedpixbuf = gtklib.get_icon_pixbuf('filedelete.ico', size)
        modifiedpixbuf = gtklib.get_icon_pixbuf('filemodify.ico', size)

        def cell_seticon(column, cell, model, iter):
            state = model.get_value(iter, 0)
            pixbuf = None
            if state == 'A':
                pixbuf = addedpixbuf
            elif state == 'R':
                pixbuf = removedpixbuf
            elif state == 'M':
                pixbuf = modifiedpixbuf
            cell.set_property('pixbuf', pixbuf)

        column.set_cell_data_func(iconcell, cell_seticon)

        list_frame = gtk.Frame()
        list_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(filelist_tree)
        flbox = gtk.VBox()
        list_frame.add(flbox)
        self.parent_box = gtk.VBox()
        flbox.pack_start(self.parent_box, False, False)
        flbox.pack_start(scroller)

        btn = gtk.CheckButton(_('Diff to second Parent'))
        btn.connect('toggled', self.parent_toggled)
        # don't pack btn yet to keep it initially invisible
        self.parent_button = btn

        self._hpaned = gtk.HPaned()
        self._hpaned.pack1(list_frame, True, True)
        self._hpaned.pack2(details_frame_parent, True, True)
        self._hpaned.set_position(self._setting_hpos)

        details_frame_parent.pack_start(details_frame, True, True)

        if embedded:
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
        def make_texttag(name, **kwargs):
            'Helper function generating a TextTag'
            tag = gtk.TextTag(name)
            for key, value in kwargs.iteritems():
                key = key.replace("_","-")
                try:
                    tag.set_property(key, value)
                except TypeError:
                    print "Warning the property %s is unsupported in" % key
                    print "this version of pygtk"
            return tag

        tag_table = self._buffer.get_tag_table()

        tag_table.add(make_texttag('diff', font=self.rawfonts['fontdiff']))
        tag_table.add(make_texttag('blue', foreground='blue'))
        if self.colorstyle == 'background':
            tag_table.add(make_texttag('red',
                                       paragraph_background=gtklib.PRED))
            tag_table.add(make_texttag('green',
                                       paragraph_background=gtklib.PGREEN))
        elif self.colorstyle == 'none':
            tag_table.add(make_texttag('red'))
            tag_table.add(make_texttag('green'))
        else:
            tag_table.add(make_texttag('red', foreground=gtklib.DRED))
            tag_table.add(make_texttag('green', foreground=gtklib.DGREEN))
        tag_table.add(make_texttag('black', foreground='black'))
        tag_table.add(make_texttag('greybg',
                                   paragraph_background='grey',
                                   weight=pango.WEIGHT_BOLD))
        tag_table.add(make_texttag('yellowbg', background='yellow'))

        issuelink_tag = make_texttag('issuelink', foreground='blue',
                                     underline=pango.UNDERLINE_SINGLE)
        issuelink_tag.connect('event', self.issuelink_event)
        tag_table.add(issuelink_tag)
        urllink_tag = make_texttag('urllink', foreground='blue',
                                     underline=pango.UNDERLINE_SINGLE)
        urllink_tag.connect('event', self.urllink_event)
        tag_table.add(urllink_tag)
        csetlink_tag = make_texttag('csetlink', foreground='blue',
                                    underline=pango.UNDERLINE_SINGLE)
        csetlink_tag.connect('event', self.csetlink_event)
        tag_table.add(csetlink_tag)

    def urllink_event(self, tag, widget, event, liter):
        if event.type != gtk.gdk.BUTTON_RELEASE:
            return
        text = self.get_link_text(tag, widget, liter)
        shlib.browse_url(text)

    def issuelink_event(self, tag, widget, event, liter):
        if event.type != gtk.gdk.BUTTON_RELEASE:
            return
        text = self.get_link_text(tag, widget, liter)
        if not text:
            return
        link = self.repo.ui.config('tortoisehg', 'issue.link')
        if link:
            groups = self.issuedict.get(text, [text])
            link, num = re.subn(r'\{(\d+)\}', lambda m:
                groups[int(m.group(1))], link)
            if not num:
                link += text
            shlib.browse_url(link)

    def csetlink_event(self, tag, widget, event, liter):
        if event.type != gtk.gdk.BUTTON_RELEASE:
            return
        text = self.get_link_text(tag, widget, liter)
        if not text:
            return
        try:
            rev = self.repo[text].rev()
            if self.graphview:
                self.graphview.set_revision_id(rev, load=True)
            else:
                self.load_details(rev)
        except error.RepoError:
            pass

    def get_link_text(self, tag, widget, liter):
        text_buffer = widget.get_buffer()
        beg = liter.copy()
        while not beg.begins_tag(tag):
            beg.backward_char()
        end = liter.copy()
        while not end.ends_tag(tag):
            end.forward_char()
        text = text_buffer.get_text(beg, end)
        return text

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
        except error.LookupError:
            has_filelog = False
        self.ann_menu.set_sensitive(has_filelog)
        self.msave.set_sensitive(has_filelog)
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

    def file_row_act(self, tree, path, column):
        self.diff_file_rev(None)
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
        if not result:
            return
        try:
            q = Queue.Queue()
            hglib.hgcmd_toq(q, 'cat', '--rev',
                str(self.currev), '--output', hglib.fromutf(result), self.curfile)
        except (util.Abort, IOError), e:
            gdialog.Prompt(_('Unable to save file'), str(e), self).run()

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
            path = hglib.escapepath(self.curfile)
            fname = hglib.toutf(path)
            opts = {'pats': [fname]}
            explorer = self.glog_parent
            explorer.filter = 'custom'
            explorer.filtercombo.set_active(1)
            explorer.filterentry.set_text(fname)
            explorer.filterbar.get_button('custom').set_active(True)
            explorer.filter_entry_activated(explorer.filterentry,
                                            explorer.filtercombo)
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
        cmdline = ['hg', 'revert', '--verbose', '--rev', str(rev), '--', self.curfile]
        dlg = hgcmd.CmdDialog(cmdline)
        dlg.run()
        dlg.hide()
        shlib.shell_notify([self.repo.wjoin(self.curfile)])

    def add_to_popup(self, textview, menu):
        menu.append(gtk.SeparatorMenuItem())
        check = self.textview.get_wrap_mode() == gtk.WRAP_WORD
        menu.append(gtklib.create_menuitem(_('Enable _Wordwrap'),
                                           self.wordwrap_activated,
                                           ascheck=True, check=check))
        menu.show_all()

    def wordwrap_activated(self, menuitem):
        mode = self.textview.get_wrap_mode() != gtk.WRAP_WORD \
                    and gtk.WRAP_WORD or gtk.WRAP_NONE
        self.textview.set_wrap_mode(mode)
