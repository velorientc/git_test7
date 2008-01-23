#
# changeset.py - Changeset dialog for TortoiseHg
#
# Copyright 2008 Steve Borho <steve@borho.org>
#

import os
import subprocess
import sys
import time

import pygtk
pygtk.require('2.0')
import gtk
import gobject
import pango
import StringIO

from mercurial.i18n import _
from mercurial.node import *
from mercurial import cmdutil, util, ui, hg, commands, patch
from gdialog import *
from hgcmd import CmdDialog


class ChangeSet(GDialog):
    """GTK+ based dialog for displaying repository logs
    """
    def get_title(self):
        title = os.path.basename(self.repo.root) + ' changeset '
        title += self.opts['rev'][0]
        return title

    def get_icon(self):
        return 'menushowchanged.ico'

    def get_tbbuttons(self):
        self.parent_toggle = gtk.ToggleToolButton(gtk.STOCK_UNDO)
        self.parent_toggle.set_use_underline(True)
        self.parent_toggle.set_label('_other parent')
        self.parent_toggle.set_tooltip(self.tooltips, 'diff other parent')
        self.parent_toggle.set_sensitive(False)
        self.parent_toggle.set_active(False)
        self.parent_toggle.connect('toggled', self._parent_toggled)
        return [self.parent_toggle]

    def _parent_toggled(self, button):
        self.load_details(self.currev)

    def prepare_display(self):
        self.currow = None
        self.graphview = None
        self.glog_parent = None
        node0, node1 = cmdutil.revpair(self.repo, self.opts.get('rev'))
        self.load_details(self.repo.changelog.rev(node0))

    def save_settings(self):
        settings = GDialog.save_settings(self)
        settings['changeset'] = self._hpaned.get_position()
        return settings

    def load_settings(self, settings):
        GDialog.load_settings(self, settings)
        if settings and 'changeset' in settings:
            self._setting_hpos = settings['changeset']
        else:
            self._setting_hpos = -1

    def load_details(self, rev):
        '''Load selected changeset details into buffer and filelist'''
        self.currev = rev
        self._buffer.set_text('')
        self._filelist.clear()

        parents = [x for x in self.repo.changelog.parentrevs(rev) \
                if x != nullrev]
        self.parents = parents
        title = self.get_title()
        if len(parents) == 2:
            self.parent_toggle.set_sensitive(True)
            if self.parent_toggle.get_active():
                title += ':' + str(self.parents[1])
            else:
                title += ':' + str(self.parents[0])
        else:
            self.parent_toggle.set_sensitive(False)
            if self.parent_toggle.get_active():
                # Parent button must be pushed out, but this
                # will cause load_details to be called again
                # so we exit out to prevent recursion.
                self.parent_toggle.set_active(False)
                return

        ctx = self.repo.changectx(rev)
        if not ctx:
            self._last_rev = None
            return False
        self.set_title(title)
        self.textview.freeze_child_notify()
        try:
            self._fill_buffer(self._buffer, rev, ctx, self._filelist)
        finally:
            self.textview.thaw_child_notify()

    def _fill_buffer(self, buf, rev, ctx, filelist):
        def title_line(title, text, tag):
            pad = ' ' * (20 - len(title))
            buf.insert_with_tags_by_name(eob, title + pad + text, tag)
            buf.insert(eob, "\n")

        # TODO: Add toggle for gmtime/localtime
        eob = buf.get_end_iter()
        date = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ctx.date()[0]))
        change = str(rev) + ':' + short(ctx.node())
        tags = ' '.join(ctx.tags())
        parents = self.parents

        title_line('changeset:', change, 'changeset')
        if ctx.branch() != 'default':
            title_line('branch:', ctx.branch(), 'greybg')
        title_line('user:', ctx.user(), 'changeset')
        title_line('date:', date, 'date')
        for p in parents:
            change = str(p) + ':' + short(self.repo.changelog.node(p))
            title = 'parent:'
            title += ' ' * (20 - len(title))
            buf.insert_with_tags_by_name(eob, title, 'parent')
            buf.insert_with_tags_by_name(eob, change, 'link')
            buf.insert(eob, "\n")
        for n in self.repo.changelog.children(ctx.node()):
            childrev = self.repo.changelog.rev(n)
            change = str(childrev) + ':' + short(n)
            title = 'child:'
            title += ' ' * (20 - len(title))
            buf.insert_with_tags_by_name(eob, title, 'parent')
            buf.insert_with_tags_by_name(eob, change, 'link')
            buf.insert(eob, "\n")
        for n in self.repo.changelog.children(ctx.node()):
            childrev = self.repo.changelog.rev(n)
        if tags: title_line('tags:', tags, 'tag')

        log = util.fromlocal(ctx.description())
        buf.insert(eob, '\n' + log + '\n\n')
        offset = eob.get_offset()

        if self.parent_toggle.get_active():
            parent = self.repo.changelog.node(parents[1])
        else:
            parent = self.repo.changelog.node(parents[0])
        out = StringIO.StringIO()
        patch.diff(self.repo, node1=parent, node2=ctx.node(),
                files=ctx.files(), fp=out)
        txt = out.getvalue()
        lines = unicode(txt, 'latin-1', 'replace').splitlines()
        fileoffs, tags, lines, statmax = self.prepare_diff(lines, offset)
        for l in lines:
            buf.insert(eob, l)

        # inserts the tags
        for name, p0, p1 in tags:
            i0 = buf.get_iter_at_offset(p0)
            i1 = buf.get_iter_at_offset(p1)
            txt = buf.get_text(i0, i1)
            buf.apply_tag_by_name(name, i0, i1)
            
        buf.create_mark('begmark', buf.get_start_iter())
        filelist.append(('[Description]', 'begmark', False, ()))

        # inserts the marks
        for f, mark, offset, stats in fileoffs:
            pos = buf.get_iter_at_offset(offset)
            buf.create_mark(mark, pos)
            filelist.append((f, mark, True, (stats[0],stats[1],statmax)))

        sob, eob = buf.get_bounds()
        buf.apply_tag_by_name("mono", sob, eob)

    def prepare_diff(self, difflines, offset):
        '''Borrowed from hgview; parses changeset diffs'''
        DIFFHDR = "=== %s ===\n"
        idx = 0
        outlines = []
        tags = []
        filespos = []
        def addtag( name, offset, length ):
            if tags and tags[-1][0] == name and tags[-1][2]==offset:
                tags[-1][2] += length
            else:
                tags.append( [name, offset, offset+length] )
        stats = [0,0]
        statmax = 0
        for i,l in enumerate(difflines):
            if l.startswith("diff"):
                f = l.split()[-1]
                txt = DIFFHDR % f
                addtag( "greybg", offset, len(txt) )
                outlines.append(txt)
                markname = "file%d" % idx
                idx += 1
                statmax = max( statmax, stats[0]+stats[1] )
                stats = [0,0]
                filespos.append(( f, markname, offset, stats ))
                offset += len(txt)
                continue
            elif l.startswith("+++"):
                continue
            elif l.startswith("---"):
                continue
            elif l.startswith("+"):
                tag = "green"
                stats[0] += 1
            elif l.startswith("-"):
                stats[1] += 1
                tag = "red"
            elif l.startswith("@@"):
                tag = "blue"
            else:
                tag = "black"
            l = l+"\n"
            length = len(l)
            addtag( tag, offset, length )
            outlines.append( l )
            offset += length
        statmax = max( statmax, stats[0]+stats[1] )
        return filespos, tags, outlines, statmax

    def link_event(self, tag, widget, event, iter):
        if event.type != gtk.gdk.BUTTON_RELEASE:
            return
        text = self.get_link_text(tag, widget, iter)
        if not text:
            return
        linkrev = long(text.split(':')[0])
        if self.graphview:
            self.graphview.set_revision_id(linkrev)
            self.graphview.scroll_to_revision(linkrev)
        else:
            self.load_details(linkrev)

    def get_link_text(self, tag, widget, iter):
        """handle clicking on a link in a textview"""
        text_buffer = widget.get_buffer()
        beg = iter.copy()
        while not beg.begins_tag(tag):
            beg.backward_char()
        end = iter.copy()
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
            
        _menu = gtk.Menu()
        _menu.append(create_menu('_view at revision', self._view_file_rev))
        _menu.append(create_menu('_file history', self._file_history))
        _menu.append(create_menu('_annotate file', self._ann_file))
        _menu.append(create_menu('_revert file contents', self._revert_file))
        self._file_diff_to_mark_menu = create_menu('_diff file to mark',
                self._diff_file_to_mark)
        self._file_diff_from_mark_menu = create_menu('diff file _from mark',
                self._diff_file_from_mark)
        _menu.append(self._file_diff_to_mark_menu)
        _menu.append(self._file_diff_from_mark_menu)
        _menu.show_all()
        return _menu

    def get_body(self):
        self._filemenu = self.file_context_menu()

        details_frame = gtk.Frame()
        details_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        details_frame.add(scroller)
        
        details_text = gtk.TextView()
        details_text.set_wrap_mode(gtk.WRAP_NONE)
        details_text.set_editable(False)
        details_text.modify_font(pango.FontDescription(self.fontcomment))
        scroller.add(details_text)

        self._buffer = gtk.TextBuffer()
        self.setup_tags()
        details_text.set_buffer(self._buffer)
        self.textview = details_text

        filelist_tree = gtk.TreeView()
        filesel = filelist_tree.get_selection()
        filesel.connect("changed", self._filelist_rowchanged)
        filelist_tree.connect('button-release-event',
                self._file_button_release)
        filelist_tree.connect('popup-menu', self._file_popup_menu)
        filelist_tree.connect('row-activated', self._file_row_act)

        self._filelist = gtk.ListStore(gobject.TYPE_STRING, # filename
                gobject.TYPE_PYOBJECT, # mark
                gobject.TYPE_PYOBJECT, # give cmenu
                gobject.TYPE_PYOBJECT  # diffstats
                )
        filelist_tree.set_model(self._filelist)
        column = gtk.TreeViewColumn('Files', gtk.CellRendererText(), text=0)
        filelist_tree.append_column(column)

        list_frame = gtk.Frame()
        list_frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scroller = gtk.ScrolledWindow()
        scroller.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroller.add(filelist_tree)
        list_frame.add(scroller)

        self._hpaned = gtk.HPaned()
        self._hpaned.pack1(details_frame, True, True)
        self._hpaned.pack2(list_frame, True, True)
        self._hpaned.set_position(self._setting_hpos)
        return self._hpaned

    def setup_tags(self):
        """Creates the tags to be used inside the TextView"""
        def make_texttag( name, **kwargs ):
            """Helper function generating a TextTag"""
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

        tag_table.add( make_texttag('changeset', foreground='#000090',
                paragraph_background='#F0F0F0'))
        tag_table.add(make_texttag('date', foreground='#000090',
                paragraph_background='#F0F0F0'))
        tag_table.add(make_texttag('tag', foreground='#000090',
                paragraph_background='#F0F0F0'))
        tag_table.add(make_texttag('files', foreground='#5C5C5C',
                paragraph_background='#F0F0F0'))
        tag_table.add(make_texttag('parent', foreground='#000090',
                paragraph_background='#F0F0F0'))

        tag_table.add( make_texttag( "mono", family="Monospace" ))
        tag_table.add( make_texttag( "blue", foreground='blue' ))
        tag_table.add( make_texttag( "red", foreground='red' ))
        tag_table.add( make_texttag( "green", foreground='darkgreen' ))
        tag_table.add( make_texttag( "black", foreground='black' ))
        tag_table.add( make_texttag( "greybg",
                                     paragraph_background='grey',
                                     weight=pango.WEIGHT_BOLD ))
        tag_table.add( make_texttag( "yellowbg", background='yellow' ))
        link_tag = make_texttag( "link", foreground="blue",
                                 underline=pango.UNDERLINE_SINGLE )
        link_tag.connect("event", self.link_event )
        tag_table.add( link_tag )

    def _filelist_rowchanged(self, sel):
        model, iter = sel.get_selected()
        if not iter:
            return
        # scroll to file in details window
        mark = self._buffer.get_mark(model[iter][1])
        self.textview.scroll_to_mark(mark, 0.0, True, 0.0, 0.0)
        if model[iter][2]:
            self.curfile = model[iter][0]
        else:
            self.curfile = None

    def _file_button_release(self, widget, event):
        if event.button == 3 and not (event.state & (gtk.gdk.SHIFT_MASK |
            gtk.gdk.CONTROL_MASK)):
            self._file_popup_menu(widget, event.button, event.time)
        return False

    def _file_popup_menu(self, treeview, button=0, time=0):
        if self.curfile is None:
            return
        if self.graphview:
            is_mark = self.graphview.get_mark_rev() is not None
        else:
            is_mark = False
        self._file_diff_to_mark_menu.set_sensitive(is_mark)
        self._file_diff_from_mark_menu.set_sensitive(is_mark)
        self._filemenu.popup(None, None, None, button, time)
        return True

    def _file_row_act(self, tree, path, column) :
        """Default action is the first entry in the context menu
        """
        self._filemenu.get_children()[0].activate()
        return True

    def _view_file_rev(self, menuitem):
        '''User selected view file revision from the file list context menu'''
        # TODO
        rev = self.currev
        parents = self.parents
        if len(parents) == 0:
            parent = rev-1
        else:
            parent = parents[0]
        pair = '%u:%u' % (parent, rev)
        self._node1, self._node2 = cmdutil.revpair(self.repo, [pair])
        self._view_file('M', self.curfile, force_left=False)

    def _diff_file_to_mark(self, menuitem):
        '''User selected diff to mark from the file list context menu'''
        from status import GStatus
        from gtools import cmdtable
        rev0 = self.graphview.get_mark_rev()
        rev1 = self.currev
        statopts = self.merge_opts(cmdtable['gstatus|gst'][1],
                ('include', 'exclude', 'git'))
        statopts['rev'] = ['%u:%u' % (rev1, rev0)]
        statopts['modified'] = True
        statopts['added'] = True
        statopts['removed'] = True
        dialog = GStatus(self.ui, self.repo, self.cwd, [self.curfile],
                statopts, False)
        dialog.display()
        return True

    def _diff_file_from_mark(self, menuitem):
        '''User selected diff from mark from the file list context menu'''
        from status import GStatus
        from gtools import cmdtable
        rev0 = self.graphview.get_mark_rev()
        rev1 = self.currev
        statopts = self.merge_opts(cmdtable['gstatus|gst'][1],
                ('include', 'exclude', 'git'))
        statopts['rev'] = ['%u:%u' % (rev0, rev1)]
        statopts['modified'] = True
        statopts['added'] = True
        statopts['removed'] = True
        dialog = GStatus(self.ui, self.repo, self.cwd, [self.curfile],
                statopts, False)
        dialog.display()

    def _ann_file(self, menuitem):
        '''User selected diff from mark from the file list context menu'''
        from datamine import DataMineDialog
        rev = self.currev
        dialog = DataMineDialog(self.ui, self.repo, self.cwd, [], {}, False)
        dialog.display()
        dialog.add_annotate_page(self.curfile, str(rev))

    def _file_history(self, menuitem):
        '''User selected file history from file list context menu'''
        if self.glog_parent:
            # If this changeset browser is embedded in glog, send
            # send this event to the main app
            self.glog_parent.custombutton.set_active(True)
            self.glog_parent.opts['rev'] = None
            self.glog_parent.reload_log({'pats' : [self.curfile]})
        else:
            # Else launch our own GLog instance
            from history import GLog
            dialog = GLog(self.ui, self.repo, self.cwd, [self.repo.root],
                    {}, False)
            dialog.open_with_file(self.curfile)
            dialog.display()

    def _revert_file(self, menuitem):
        '''User selected file revert from the file list context menu'''
        rev = self.currev
        dialog = Confirm('revert file to old revision', [], self,
                'Revert %s to contents at revision %d?' % (self.curfile, rev))
        if dialog.run() == gtk.RESPONSE_NO:
            return
        cmdline = ['hg', 'revert', '--verbose', '--rev', str(rev), self.curfile]
        self.restore_cwd()
        dlg = CmdDialog(cmdline)
        dlg.run()
        dlg.hide()
        shell_notify([self.curfile])

def run(root='', cwd='', files=[], **opts):
    u = ui.ui()
    u.updateopts(debug=False, traceback=False)
    repo = hg.repository(u, path=root)

    dialog = ChangeSet(u, repo, cwd, files, opts, True)
    dialog.display()

    gtk.gdk.threads_init()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()

if __name__ == "__main__":
    import sys
    opts = {}
    opts['root'] = len(sys.argv) > 1 and sys.argv[1] or os.getcwd()
    opts['rev'] = ['750']
    run(**opts)
