# chunks.py - status/commit chunk handling for TortoiseHg
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright 2007 TK Soh <teekaysoh@gmail.com>
# Copyright 2008 Steve Borho <steve@borho.org>
# Copyright 2008 Emmanuel Rosa <goaway1000@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk
import pango
import cStringIO

from mercurial import cmdutil, util, patch, mdiff, error

from tortoisehg.util import hglib, hgshelve
from tortoisehg.util.i18n import _

from tortoisehg.hgtk import gtklib

# diffmodel row enumerations
DM_REJECTED  = 0
DM_DISP_TEXT = 1
DM_IS_HEADER = 2
DM_PATH      = 3
DM_CHUNK_ID  = 4
DM_FONT      = 5


def hunk_markup(text):
    'Format a diff hunk for display in a TreeView row with markup'
    hunk = ''
    # don't use splitlines, should split with only LF for the patch
    lines = hglib.tounicode(text).split(u'\n')
    for line in lines:
        line = hglib.toutf(line[:512]) + '\n'
        if line.startswith('---') or line.startswith('+++'):
            hunk += gtklib.markup(line, color=gtklib.DBLUE)
        elif line.startswith('-'):
            hunk += gtklib.markup(line, color=gtklib.DRED)
        elif line.startswith('+'):
            hunk += gtklib.markup(line, color=gtklib.DGREEN)
        elif line.startswith('@@'):
            hunk = gtklib.markup(line, color=gtklib.DORANGE)
        else:
            hunk += gtklib.markup(line)
    return hunk


def hunk_unmarkup(text):
    'Format a diff hunk for display in a TreeView row without markup'
    hunk = ''
    # don't use splitlines, should split with only LF for the patch
    lines = hglib.tounicode(text).split(u'\n')
    for line in lines:
        hunk += gtklib.markup(hglib.toutf(line[:512])) + '\n'
    return hunk


def check_max_diff(ctx, wfile):
    lines = []
    try:
        fctx = ctx.filectx(wfile)
        size = fctx.size()
    except (EnvironmentError, error.LookupError):
        return []
    if size > hglib.getmaxdiffsize(ctx._repo.ui):
        # Fake patch that displays size warning
        lines = ['diff --git a/%s b/%s\n' % (wfile, wfile)]
        lines.append(_('File is larger than the specified max size.\n'))
        lines.append(_('Hunk selection is disabled for this file.\n'))
        lines.append('--- a/%s\n' % wfile)
        lines.append('+++ b/%s\n' % wfile)
    elif '\0' in fctx.data():
        # Fake patch that displays binary file warning
        lines = ['diff --git a/%s b/%s\n' % (wfile, wfile)]
        lines.append(_('File is binary.\n'))
        lines.append(_('Hunk selection is disabled for this file.\n'))
        lines.append('--- a/%s\n' % wfile)
        lines.append('+++ b/%s\n' % wfile)
    return lines


class chunks(object):

    def __init__(self, stat):
        self.stat = stat
        self.filechunks = {}
        self.diffmodelfile = None
        self._difftree = None

    def difftree(self):
        if self._difftree != None:
            return self._difftree

        self.diffmodel = gtk.ListStore(
                bool, # DM_REJECTED
                str,  # DM_DISP_TEXT
                bool, # DM_IS_HEADER
                str,  # DM_PATH
                int,  # DM_CHUNK_ID
                pango.FontDescription # DM_FONT
            )

        dt = gtk.TreeView(self.diffmodel)
        self._difftree = dt
        
        dt.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        dt.set_headers_visible(False)
        dt.set_enable_search(False)
        if getattr(dt, 'enable-grid-lines', None) is not None:
            dt.set_property('enable-grid-lines', True)

        dt.connect('row-activated', self.diff_tree_row_act)
        dt.connect('copy-clipboard', self.copy_to_clipboard)

        cell = gtk.CellRendererText()
        diffcol = gtk.TreeViewColumn('diff', cell)
        diffcol.set_resizable(True)
        diffcol.add_attribute(cell, 'markup', DM_DISP_TEXT)

        # differentiate header chunks
        cell.set_property('cell-background', gtklib.STATUS_HEADER)
        diffcol.add_attribute(cell, 'cell_background_set', DM_IS_HEADER)
        self.headerfont = self.stat.difffont.copy()
        self.headerfont.set_weight(pango.WEIGHT_HEAVY)

        # differentiate rejected hunks
        self.rejfont = self.stat.difffont.copy()
        self.rejfont.set_weight(pango.WEIGHT_LIGHT)
        diffcol.add_attribute(cell, 'font-desc', DM_FONT)
        cell.set_property('background', gtklib.STATUS_REJECT_BACKGROUND)
        cell.set_property('foreground', gtklib.STATUS_REJECT_FOREGROUND)
        diffcol.add_attribute(cell, 'background-set', DM_REJECTED)
        diffcol.add_attribute(cell, 'foreground-set', DM_REJECTED)
        dt.append_column(diffcol)
        
        return dt

    def __getitem__(self, wfile):
        return self.filechunks[wfile]

    def __contains__(self, wfile):
        return wfile in self.filechunks

    def clear_filechunks(self):
        self.filechunks = {}

    def clear(self):
        self.diffmodel.clear()
        self.diffmodelfile = None

    def del_file(self, wfile):
        if wfile in self.filechunks:
            del self.filechunks[wfile]

    def update_chunk_state(self, wfile, selected):
        if wfile not in self.filechunks:
            return
        chunks = self.filechunks[wfile]
        for chunk in chunks:
            chunk.active = selected
        if wfile != self.diffmodelfile:
            return
        for n, chunk in enumerate(chunks):
            if n == 0:
                continue
            self.diffmodel[n][DM_REJECTED] = not selected
            self.update_diff_hunk(self.diffmodel[n])
        self.update_diff_header(self.diffmodel, wfile, selected)

    def update_diff_hunk(self, row):
        'Update the contents of a diff row based on its chunk state'
        wfile = row[DM_PATH]
        chunks = self.filechunks[wfile]
        chunk = chunks[row[DM_CHUNK_ID]]
        buf = cStringIO.StringIO()
        chunk.pretty(buf)
        buf.seek(0)
        if chunk.active:
            row[DM_REJECTED] = False
            row[DM_FONT] = self.stat.difffont
            row[DM_DISP_TEXT] = hunk_markup(buf.read())
        else:
            row[DM_REJECTED] = True
            row[DM_FONT] = self.rejfont
            row[DM_DISP_TEXT] = hunk_unmarkup(buf.read())

    def update_diff_header(self, dmodel, wfile, selected):
        try:
            chunks = self.filechunks[wfile]
        except IndexError:
            return
        lasthunk = len(chunks)-1
        sel = lambda x: x >= lasthunk or not dmodel[x+1][DM_REJECTED]
        newtext = chunks[0].selpretty(sel)
        if not selected:
            newtext = "<span foreground='" + gtklib.STATUS_REJECT_FOREGROUND + \
                "'>" + newtext + "</span>"
        dmodel[0][DM_DISP_TEXT] = newtext

    def get_chunks(self, wfile): # new
        if wfile in self.filechunks:
            chunks = self.filechunks[wfile]
        else:
            chunks = self.read_file_chunks(wfile)
            if chunks:
                for c in chunks:
                    c.active = True
                self.filechunks[wfile] = chunks
        return chunks

    def update_hunk_model(self, wfile, checked):
        # Read this file's diffs into hunk selection model
        self.diffmodel.clear()
        self.diffmodelfile = wfile
        if not self.stat.is_merge():
            self.append_diff_hunks(wfile, checked)

    def len(self):
        return len(self.diffmodel)

    def append_diff_hunks(self, wfile, checked):
        'Append diff hunks of one file to the diffmodel'
        chunks = self.read_file_chunks(wfile)
        if not chunks:
            if wfile in self.filechunks:
                del self.filechunks[wfile]
            return 0

        rows = []
        for n, chunk in enumerate(chunks):
            if isinstance(chunk, hgshelve.header):
                # header chunk is always active
                chunk.active = True
                rows.append([False, '', True, wfile, n, self.headerfont])
                if chunk.special():
                    chunks = chunks[:1]
                    break
            else:
                # chunks take file's selection state by default
                chunk.active = checked
                rows.append([False, '', False, wfile, n, self.stat.difffont])

        # recover old chunk selection/rejection states, match fromline
        if wfile in self.filechunks:
            ochunks = self.filechunks[wfile]
            next = 1
            for oc in ochunks[1:]:
                for n in xrange(next, len(chunks)):
                    nc = chunks[n]
                    if oc.fromline == nc.fromline:
                        nc.active = oc.active
                        next = n+1
                        break
                    elif nc.fromline > oc.fromline:
                        break

        self.filechunks[wfile] = chunks

        # Set row status based on chunk state
        rej, nonrej = False, False
        for n, row in enumerate(rows):
            if not row[DM_IS_HEADER]:
                if chunks[n].active:
                    nonrej = True
                else:
                    rej = True
                row[DM_REJECTED] = not chunks[n].active
                self.update_diff_hunk(row)
            self.diffmodel.append(row)

        if len(rows) == 1:
            newvalue = checked
        else:
            newvalue = nonrej
        self.update_diff_header(self.diffmodel, wfile, newvalue)
        
        return len(rows)

    def diff_tree_row_act(self, dtree, path, column):
        'Row in diff tree (hunk) activated/toggled'
        dmodel = dtree.get_model()
        row = dmodel[path]
        wfile = row[DM_PATH]
        checked = self.stat.get_checked(wfile)
        try:
            chunks = self.filechunks[wfile]
        except IndexError:
            pass
        chunkrows = xrange(1, len(chunks))
        if row[DM_IS_HEADER]:
            for n, chunk in enumerate(chunks[1:]):
                chunk.active = not checked
                self.update_diff_hunk(dmodel[n+1])
            newvalue = not checked
            partial = False
        else:
            chunk = chunks[row[DM_CHUNK_ID]]
            chunk.active = not chunk.active
            self.update_diff_hunk(row)
            rej = [ n for n in chunkrows if dmodel[n][DM_REJECTED] ]
            nonrej = [ n for n in chunkrows if not dmodel[n][DM_REJECTED] ]
            newvalue = nonrej and True or False
            partial = rej and nonrej and True or False
        self.update_diff_header(dmodel, wfile, newvalue)

        self.stat.update_check_state(wfile, partial, newvalue)

    def get_wfile(self, dtree, path):
        dmodel = dtree.get_model()
        row = dmodel[path]
        wfile = row[DM_PATH]
        return wfile

    def save(self, files, patchfilename):
        buf = cStringIO.StringIO()
        dmodel = self.diffmodel
        for wfile in files:
            if wfile in self.filechunks:
                chunks = self.filechunks[wfile]
            else:
                chunks = self.read_file_chunks(wfile)
                for c in chunks:
                    c.active = True
            for i, chunk in enumerate(chunks):
                if i == 0:
                    chunk.write(buf)
                elif chunk.active:
                    chunk.write(buf)
        buf.seek(0)
        try:
            try:
                fp = open(patchfilename, 'wb')
                fp.write(buf.read())
            except OSError:
                pass
        finally:
            fp.close()

    def copy_to_clipboard(self, treeview):
        'Write highlighted hunks to the clipboard'
        if not treeview.is_focus():
            w = self.stat.get_focus()
            w.emit('copy-clipboard')
            return False
        saves = {}
        model, tpaths = treeview.get_selection().get_selected_rows()
        for row, in tpaths:
            wfile, cid = model[row][DM_PATH], model[row][DM_CHUNK_ID]
            if wfile not in saves:
                saves[wfile] = [cid]
            else:
                saves[wfile].append(cid)
        fp = cStringIO.StringIO()
        for wfile in saves.keys():
            chunks = self[wfile]
            chunks[0].write(fp)
            for cid in saves[wfile]:
                if cid != 0:
                    chunks[cid].write(fp)
        fp.seek(0)
        self.stat.clipboard.set_text(fp.read())

    def read_file_chunks(self, wfile):
        'Get diffs of working file, parse into (c)hunks'
        difftext = cStringIO.StringIO()
        pfile = util.pconvert(wfile)
        lines = check_max_diff(self.stat.get_ctx(), pfile)
        if lines:
            difftext.writelines(lines)
            difftext.seek(0)
        else:
            matcher = cmdutil.matchfiles(self.stat.repo, [pfile])
            diffopts = mdiff.diffopts(git=True, nodates=True)
            try:
                node1, node2 = self.stat.nodes()
                for s in patch.diff(self.stat.repo, node1, node2,
                        match=matcher, opts=diffopts):
                    difftext.writelines(s.splitlines(True))
            except (IOError, error.RepoError, error.LookupError, util.Abort), e:
                self.stat.stbar.set_text(str(e))
            difftext.seek(0)
        return hgshelve.parsepatch(difftext)
