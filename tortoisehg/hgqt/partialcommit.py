# partialcommit.py - commit extension for partial commits (change selection)
#
# Copyright 2012 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

from mercurial.i18n import _
from mercurial.node import hex, nullid
from mercurial import patch, commands, extensions, scmutil, encoding, context
from mercurial import error, bookmarks, merge

#
# Note all the translatable strings in this file are copies of Mercurial
# strings which are translated by Mercurial's i18n module.
#

def makememctx(repo, parents, text, user, date, extra, files, store):
    def getfilectx(repo, memctx, path):
        if path in memctx.files():
            # use patched file contents
            data, (islink, isexec), copied = store.getfile(path)
        else:
            # fall back to workingctx
            wctx = repo[None]
            if path not in wctx:
                raise IOError
            fctx = wctx[path]
            data = fctx.data()
            islink = 'l' in fctx.flags()
            isexec = 'x' in fctx.flags()
            copied = repo.dirstate.copied(path)
        return context.memfilectx(path, data, islink, isexec, copied)

    return context.memctx(repo, parents, text, files, getfilectx, user,
                          date, extra)

def partialcommit(orig, ui, repo, *pats, **opts):
    # partial commit requires explicit file list (no patterns)
    # working folder must have a single parent
    # does not emit as many warnings and messages as the real commit
    # opts['message'] is mandatory
    if 'partials' not in opts:
        return orig(ui, repo, *pats, **opts)

    if opts.get('subrepos'):
        # Let --subrepos on the command line override config setting.
        ui.setconfig('ui', 'commitsubrepos', True)

    files = [scmutil.canonpath(repo.root, repo.root, f) for f in pats]

    ms = merge.mergestate(repo)
    for f in files:
        if f in ms and ms[f] == 'u':
            raise error.Abort(_("unresolved merge conflicts "
                                "(see hg help resolve)"))

    patchfile = opts['partials']
    fp = open(patchfile, 'rb')

    newrev = None
    store = patch.filestore()
    try:
        # TODO: likely need to copy .hgsub/.hgsubstate code from
        # localrepo.commit() lines 1303-1355, 1396-1404

        p1, p2 = repo.dirstate.parents()
        hookp1, hookp2 = hex(p1), (p2 != nullid and hex(p2) or '')
        repo.hook("precommit", throw=True, parent1=hookp1, parent2=hookp2)

        extra = {'branch': encoding.fromlocal(repo[None].branch())}
        if opts.get('close_branch'):
            if p1 not in repo.branchheads():
                # The topo heads set is included in the branch heads set of the
                # current branch, so it's sufficient to test branchheads
                raise error.Abort(_('can only close branch heads'))
            extra['close'] = 1

        # patch files in tmp directory
        try:
            patch.patchrepo(ui, repo, repo['.'], store, fp, 1, None)
        except patch.PatchError, e:
            raise error.Abort(str(e))

        # create new revision from memory
        memctx = makememctx(repo, (p1, p2), opts['message'],
                            opts.get('user'), opts.get('date'), extra,
                            files, store)

        newrev = memctx.commit()
    finally:
        store.close()
        fp.close()
        os.unlink(patchfile)

    # move working directory to new revision
    if newrev:
        wlock = repo.wlock()
        try:
            bookmarks.update(repo, [p1, p2], newrev)
            repo.setparents(newrev)
            ctx = repo[newrev]
            repo.dirstate.rebuild(ctx.node(), ctx.manifest())
            ms.reset()
        finally:
            wlock.release()

    def commithook(node=hex(newrev), parent1=hookp1, parent2=hookp2):
        repo.hook("commit", node=node, parent1=parent1, parent2=parent2)
    repo._afterlock(commithook)
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
