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
        self.ucontents = None
        self.error = None
        self.olddata = None
        self.diff = None
        self.flabel = u''
        self.elabel = u''
        try:
            self.readStatus(ctx, ctx2, wfile, status)
        except (EnvironmentError, error.LookupError), e:
            self.error = hglib.tounicode(str(e))

    def checkMaxDiff(self, ctx, wfile, maxdiff=None):
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
        if size > maxdiff:
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

        wsub, wfileinsub, sctx = \
            hglib.getDeepestSubrepoContainingFile(wfile, ctx)
        if wsub:
            topctx = ctx
            topwfile = wfile
            ctx = sctx
            wfile = wfileinsub
        else:
            topctx = ctx
            topwfile = wfile
            
        absfile = repo.wjoin(os.path.join(wsub or '',wfile))
        if (wfile in ctx and 'l' in ctx.flags(wfile)) or \
           os.path.islink(absfile):
            if wfile in ctx:
                data = ctx[wfile].data()
            else:
                data = os.readlink(absfile)
            self.contents = data
            self.flabel += _(' <i>(is a symlink)</i>')
            return

        if status is None:
            status = getstatus(repo, ctx.p1().node(), ctx.node(), wfile)
        if ctx2 is None:
            ctx2 = ctx.p1()

        if status == 'S':
            try:
                from mercurial import subrepo, commands

                def genSubrepoRevChangedDescription(subrelpath, sfrom, sto):
                    """Generate a subrepository revision change description"""
                    out = []
                    def getLog(_ui, srepo, opts):
                        _ui.pushbuffer()
                        commands.log(_ui, srepo, **opts)
                        return _ui.popbuffer()
                    opts = {'date':None, 'user':None, 'rev':[sfrom]}
                    subabspath = os.path.join(repo.root, subrelpath)
                    missingsub = not os.path.isdir(subabspath)
                    def isinitialrevision(rev):
                        return all([el == '0' for el in rev])
                    if isinitialrevision(sfrom):
                        sfrom = ''
                    if isinitialrevision(sto):
                        sto = ''
                    if not sfrom and not sto:
                        sstatedesc = 'new'
                        out.append(_('Subrepo created and set to initial revision.') + u'\n\n')
                        return out, sstatedesc
                    elif not sfrom:
                        sstatedesc = 'new'
                        out.append(_('Subrepo initialized to revision:') + u'\n\n')
                    elif not sto:
                        sstatedesc = 'removed'
                        out.append(_('Subrepo removed from repository.') + u'\n\n')
                        return out, sstatedesc
                    elif sfrom == sto:
                        sstatedesc = 'unchanged'
                        out.append(_('Subrepo was not changed.') + u'\n\n')
                        out.append(_('Subrepo state is:') + u'\n')
                        if missingsub:
                            out.append(hglib.tounicode(_('changeset: %s') % sfrom + '\n'))
                        else:
                            out.append(hglib.tounicode(getLog(_ui, srepo, opts)))
                        return out, sstatedesc
                    else:
                        sstatedesc = 'changed'

                        out.append(_('Revision has changed from:') + u'\n\n')
                        if missingsub:
                            out.append(hglib.tounicode(_('changeset: %s') % sfrom + '\n'))
                        else:
                            out.append(hglib.tounicode(getLog(_ui, srepo, opts)))

                        out.append(_('To:') + u'\n')
                    if missingsub:
                        stolog = _('changeset: %s') % sto + '\n\n'
                        stolog += _('Subrepository not found in working directory.') + '\n'
                        stolog += _('Further subrepository revision information cannot be retrieved.') + '\n'
                    else:
                        opts['rev'] = [sto]
                        stolog = getLog(_ui, srepo, opts)

                    if not stolog:
                        stolog = _('Initial revision')
                    out.append(hglib.tounicode(stolog))

                    return out, sstatedesc

                srev = ctx.substate.get(wfile, subrepo.nullstate)[1]
                srepo = None
                try:
                    subabspath = os.path.join(repo.root, wfile)
                    if not os.path.isdir(subabspath):
                        sactual = ''
                    else:
                        sub = ctx.sub(wfile)
                        if isinstance(sub, subrepo.hgsubrepo):
                            srepo = sub._repo
                            sactual = srepo['.'].hex()
                        else:
                            self.error = _('Not a Mercurial subrepo, not previewable')
                            return
                except (util.Abort), e:
                    sactual = ''

                out = []
                _ui = uimod.ui()

                if srepo is None or ctx.rev() is not None:
                    data = []
                else:
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
                    subrepochange, sstatedesc = genSubrepoRevChangedDescription(wfile, sparent, srev)
                    out += subrepochange
                else:
                    sstatedesc = 'dirty'
                    if srev != sactual:
                        subrepochange, sstatedesc = \
                            genSubrepoRevChangedDescription(wfile, srev, sactual)
                        out += subrepochange
                        if data:
                            sstatedesc += ' and dirty'
                self.ucontents = u''.join(out)
                if not sactual:
                    sstatedesc = 'removed'
                lbl = {
                    'changed':   _('(is a changed sub-repository)'),
                    'unchanged':   _('(is an unchanged sub-repository)'),
                    'dirty':   _('(is a dirty sub-repository)'),
                    'new':   _('(is a new sub-repository)'),
                    'removed':   _('(is a removed sub-repository)'),
                    'changed and dirty':   _('(is a changed and dirty sub-repository)'),
                    'new and dirty':   _('(is a new and dirty sub-repository)')
                }[sstatedesc]
                self.flabel += ' <i>' + lbl + '</i>'
                if sactual:
                    lbl = _(' <a href="subrepo:%s">open...</a>')
                    self.flabel += lbl % hglib.tounicode(srepo.root)
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
                        self.contents = olddata
                self.flabel += _(' <i>(was deleted)</i>')
            else:
                self.flabel += _(' <i>(was added, now missing)</i>')
            return

        if status in ('I', '?', 'C'):
            if os.path.getsize(repo.wjoin(wfile)) > ctx._repo.maxdiff:
                self.error = mde
            else:
                data = util.posixfile(repo.wjoin(wfile), 'r').read()
                if '\0' in data:
                    self.error = 'binary file'
                else:
                    self.contents = data
            if status in ('I', '?'):
                self.flabel += _(' <i>(is unversioned)</i>')
            return

        if status in ('M', 'A'):
            res = self.checkMaxDiff(ctx, wfile, repo.maxdiff)
            if res is None:
                return
            fctx, newdata = res
            self.contents = newdata
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

        self.olddata = olddata
        newdate = util.datestr(ctx.date())
        olddate = util.datestr(ctx2.date())
        revs = [str(ctx), str(ctx2)]
        diffopts = patch.diffopts(repo.ui, {})
        diffopts.git = False
        self.diff = mdiff.unidiff(olddata, olddate, newdata, newdate,
                                  oldname, wfile, revs, diffopts)
