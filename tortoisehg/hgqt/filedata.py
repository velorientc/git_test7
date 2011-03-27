# filedata.py - generate displayable file data
#
# Copyright 2011 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial import error, match, patch, util, mdiff
from mercurial import ui as uimod

from tortoisehg.util import hglib, patchctx
from tortoisehg.hgqt.i18n import _

class FileData(object):
    def __init__(self, ctx, ctx2, wfile, status=None):
        self.contents = None
        self.error = None
        self.olddata = None
        self.diff = None
        self.flabel = u''
        self.elabel = u''
        try:
            self.readStatus(ctx, ctx2, wfile, status)
        except (EnvironmentError, error.LookupError), e:
            self.error = hglib.tounicode(str(e))

    def checkMaxDiff(self, ctx, wfile):
        p = _('File or diffs not displayed: ')
        try:
            fctx = ctx.filectx(wfile)
            if ctx.rev() is None:
                size = fctx.size()
            else:
                # fctx.size() can read all data into memory in rename cases so
                # we read the size directly from the filelog, this is deeper
                # under the API than I prefer to go, but seems necessary
                size = fctx._filelog.rawsize(fctx.filerev())
        except (EnvironmentError, error.LookupError), e:
            self.error = p + hglib.tounicode(str(e))
            return None
        if size > ctx._repo.maxdiff:
            self.error = p + _('File is larger than the specified max size.\n')
            return None
        try:
            data = fctx.data()
            if '\0' in data:
                self.error = p + _('File is binary.\n')
                return None
        except EnvironmentError, e:
            self.error = p + hglib.tounicode(str(e))
            return None
        return fctx, data

    def isValid(self):
        return self.error is None

    def readStatus(self, ctx, ctx2, wfile, status):
        def getstatus(repo, n1, n2, wfile):
            m = match.exact(repo.root, repo.getcwd(), [wfile])
            modified, added, removed = repo.status(n1, n2, match=m)[:3]
            if wfile in modified:
                return 'M'
            if wfile in added:
                return 'A'
            if wfile in removed:
                return 'R'
            if wfile in ctx:
                return 'C'
            return None

        repo = ctx._repo
        self.flabel += u'<b>%s</b>' % hglib.tounicode(wfile)

        if isinstance(ctx, patchctx.patchctx):
            self.diff = ctx.thgmqpatchdata(wfile)
            flags = ctx.flags(wfile)
            if flags in ('x', '-'):
                lbl = _("exec mode has been <font color='red'>%s</font>")
                change = (flags == 'x') and _('set') or _('unset')
                self.elabel = lbl % change
            elif flags == 'l':
                self.flabel += _(' <i>(is a symlink)</i>')
            return

        absfile = repo.wjoin(wfile)
        if (wfile in ctx and 'l' in ctx.flags(wfile)) or \
           os.path.islink(absfile):
            if wfile in ctx:
                data = ctx[wfile].data()
            else:
                data = os.readlink(absfile)
            self.contents = hglib.tounicode(data)
            self.flabel += _(' <i>(is a symlink)</i>')
            return

        if status is None:
            status = getstatus(repo, ctx.p1().node(), ctx.node(), wfile)
        if ctx2 is None:
            ctx2 = ctx.p1()

        if status == 'S':
            try:
                from mercurial import subrepo, commands

                def genSubrepoRevChangedDescription(sfrom, sto):
                    """Generate a subrepository revision change description"""
                    out = []
                    opts = {'date':None, 'user':None, 'rev':[sfrom]}
                    if not sfrom:
                        sstatedesc = 'new'
                        out.append(_('Subrepo initialized to revision:') + u'\n\n')
                    elif not sto:
                        sstatedesc = 'removed'
                        out.append(_('Subrepo removed from repository.') + u'\n\n')
                        return out, sstatedesc
                    else:
                        sstatedesc = 'changed'
                        out.append(_('Revision has changed from:') + u'\n\n')
                        _ui.pushbuffer()
                        commands.log(_ui, srepo, **opts)
                        out.append(hglib.tounicode(_ui.popbuffer()))
                        out.append(_('To:') + u'\n')
                    opts['rev'] = [sto]
                    _ui.pushbuffer()
                    commands.log(_ui, srepo, **opts)
                    stolog = _ui.popbuffer()
                    if not stolog:
                        stolog = _('Initial revision')
                    out.append(hglib.tounicode(stolog))
                    return out, sstatedesc

                srev = ctx.substate.get(wfile, subrepo.nullstate)[1]
                try:
                    sub = ctx.sub(wfile)
                    if isinstance(sub, subrepo.hgsubrepo):
                        srepo = sub._repo
                        sactual = srepo['.'].hex()
                    else:
                        self.error = _('Not a Mercurial subrepo, not previewable')
                        return
                except (util.Abort), e:
                    sub = ctx.p1().sub(wfile)
                    srepo = sub._repo
                    sactual = ''
                out = []
                _ui = uimod.ui()
                _ui.pushbuffer()
                commands.status(_ui, srepo)
                data = _ui.popbuffer()
                if data:
                    out.append(_('File Status:') + u'\n')
                    out.append(hglib.tounicode(data))
                    out.append(u'\n')
                sstatedesc = 'changed'
                if ctx.rev() is not None:
                    sparent = ctx.p1().substate.get(wfile, subrepo.nullstate)[1]
                    subrepochange, sstatedesc = genSubrepoRevChangedDescription(sparent, srev)
                    out += subrepochange
                else:
                    if srev != sactual:
                        subrepochange, sstatedesc = \
                            genSubrepoRevChangedDescription(srev, sactual)
                        out += subrepochange
                    if data:
                        sstatedesc += ' and dirty'
                self.contents = u''.join(out)
                if not sactual:
                    sstatedesc = 'removed'
                self.flabel += _(' <i>(is a %s sub-repository)</i>' % sstatedesc)
                if sactual:
                    lbl = u' <a href="subrepo:%s">%s...</a>'
                    self.flabel += lbl % (hglib.tounicode(srepo.root), _('open'))
            except (EnvironmentError, error.RepoError, util.Abort), e:
                self.error = _('Error previewing subrepo: %s') % \
                        hglib.tounicode(str(e))
            return

        # TODO: elif check if a subdirectory (for manifest tool)

        mde = _('File or diffs not displayed: ') + \
              _('File is larger than the specified max size.\n')

        if status in ('R', '!'):
            if wfile in ctx.p1():
                fctx = ctx.p1()[wfile]
                if fctx._filelog.rawsize(fctx.filerev()) > ctx._repo.maxdiff:
                    self.error = mde
                else:
                    olddata = fctx.data()
                    if '\0' in olddata:
                        self.error = 'binary file'
                    else:
                        self.contents = hglib.tounicode(olddata)
                self.flabel += _(' <i>(was deleted)</i>')
            else:
                self.flabel += _(' <i>(was added, now missing)</i>')
            return

        if status in ('I', '?', 'C'):
            if os.path.getsize(repo.wjoin(wfile)) > ctx._repo.maxdiff:
                self.error = mde
            else:
                data = open(repo.wjoin(wfile), 'r').read()
                if '\0' in data:
                    self.error = 'binary file'
                else:
                    self.contents = hglib.tounicode(data)
            if status in ('I', '?'):
                self.flabel += _(' <i>(is unversioned)</i>')
            return

        if status in ('M', 'A'):
            res = self.checkMaxDiff(ctx, wfile)
            if res is None:
                return
            fctx, newdata = res
            self.contents = hglib.tounicode(newdata)
            change = None
            for pfctx in fctx.parents():
                if 'x' in fctx.flags() and 'x' not in pfctx.flags():
                    change = _('set')
                elif 'x' not in fctx.flags() and 'x' in pfctx.flags():
                    change = _('unset')
            if change:
                lbl = _("exec mode has been <font color='red'>%s</font>")
                self.elabel = lbl % change

        if status == 'A':
            renamed = fctx.renamed()
            if not renamed:
                self.flabel += _(' <i>(was added)</i>')
                return

            oldname, node = renamed
            fr = hglib.tounicode(oldname)
            self.flabel += _(' <i>(renamed from %s)</i>') % fr
            olddata = repo.filectx(oldname, fileid=node).data()
        elif status == 'M':
            if wfile not in ctx2:
                # merge situation where file was added in other branch
                self.flabel += _(' <i>(was added)</i>')
                return
            oldname = wfile
            olddata = ctx2[wfile].data()
        else:
            return

        self.olddata = hglib.tounicode(olddata)
        newdate = util.datestr(ctx.date())
        olddate = util.datestr(ctx2.date())
        revs = [str(ctx), str(ctx2)]
        diffopts = patch.diffopts(repo.ui, {})
        diffopts.git = False
        self.diff = mdiff.unidiff(olddata, olddate, newdata, newdate,
                                  oldname, wfile, revs, diffopts)
