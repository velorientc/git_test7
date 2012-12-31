# partialcommit.py - commit extension for partial commits (change selection)
#
# Copyright 2013 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import cStringIO

from mercurial.i18n import _
from mercurial import patch, commands, extensions, scmutil, encoding, context

def makememctx(repo, parents, text, user, date, branch, files, store):
    def getfilectx(repo, memctx, path):
        try:
            # try patched file contents first
            data, (islink, isexec), copied = store.getfile(path)
        except IOError:
            # fall back to working folder contents
            wctx = repo[None]
            try:
                fctx = wctx[path]
            except error.LookupError:
                raise IOError
            data = fctx.data()
            islink = 'l' in fctx.flags()
            isexec = 'x' in fctx.flags()
            rp = fctx.renamed()
            if rp is not None:
                copied = rp[0]
            else:
                copied = None

        return context.memfilectx(path, data, islink=islink, isexec=isexec,
                                  copied=copied)
    extra = {}
    if branch:
        extra['branch'] = encoding.fromlocal(branch)
    return context.memctx(repo, parents, text, files, getfilectx, user,
                          date, extra)

def partialcommit(orig, ui, repo, *pats, **opts):
    if 'partials' not in opts:
        return orig(ui, repo, *pats, **opts)

    if opts.get('subrepos'):
        # Let --subrepos on the command line override config setting.
        ui.setconfig('ui', 'commitsubrepos', True)

    files = [scmutil.canonpath(repo.root, repo.root, f) for f in pats]

    patchfile = opts['partials']
    fp = open(patchfile, 'rb')

    newrev = None
    branch = repo[None].branch()
    store = patch.filestore()
    try:
        pctx = repo['.']

        # TODO: likely need to copy .hgsub/.hgsubstate code from
        # localrepo.commit() lines 1303-1355, 1396-1404

        # patch files in tmp directory
        try:
            patch.patchrepo(ui, repo, pctx, store, fp, 1, None)
        except patch.PatchError, e:
            raise util.Abort(str(e))

        # create new revision from memory
        memctx = makememctx(repo, (pctx.node(), None), opts['message'],
                            opts.get('user'), opts.get('date'), branch,
                            files, store)

        if opts.get('close_branch'):
            if pctx.node() not in repo.branchheads():
                # The topo heads set is included in the branch heads set of the
                # current branch, so it's sufficient to test branchheads
                raise util.Abort(_('can only close branch heads'))
            memctx._extra['close'] = 1

        # TODO: precommit hook from localrepo.commit() lines 1406-1415
        newrev = memctx.commit()
    finally:
        store.close()
        fp.close()

    # move working directory to new revision
    if newrev:
        wlock = repo.wlock()
        try:
            # TODO: bookmarks, ms.reset(), from localrepo.commit() lines 1423-1430
            repo.setparents(newrev)
            ctx = repo[newrev]
            repo.dirstate.rebuild(ctx.node(), ctx.manifest())
        finally:
            wlock.release()

    # TODO: localrepo.hook('commit') lines 1434-1437
    os.unlink(patchfile)
    return 0

# We're not using Mercurial's extension loader (so partialcommit will not
# show up in the list of extensions on traceback), so we must protect ourselves
# from multiple registrations

registered = False
def uisetup(ui):
    'Replace commit with a decorator to provide --partials option'
    global registered
    if registered:
        return
    entry = extensions.wrapcommand(commands.table, 'commit', partialcommit)
    entry[1].append(('', 'partials', '',
                     _("selected patch chunks (internal use only)")))
    registered = True
