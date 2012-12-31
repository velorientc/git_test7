# partialcommit.py - commit extension for partial commits (change selection)
#
# Copyright 2013 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import cStringIO

from mercurial.i18n import _
from mercurial import patch, hg, commands, extensions

def partialcommit(orig, ui, repo, *pats, **opts):
    if 'partials' not in opts:
        return orig(ui, repo, *pats, **opts)

    partials = opts['partials']
    fp = cStringIO.StringIO()
    patchfiles = []
    for changes in partials.values():
        patchfiles.append(changes.filename())
        changes.write(fp)
        for chunk in changes.hunks:
            if not chunk.excluded:
                chunk.write(fp)
    fp.seek(0)

    # TODO: --close-branch and other options

    repo = hg.repository(ui, repo.root, False)
    store = patch.filestore()
    newrev = None
    try:
        pctx = repo['.']

        # patch files in tmp directory
        try:
            patch.patchrepo(ui, repo, pctx, store, fp, 1, partials.keys())
        except patch.PatchError, e:
            raise util.Abort(str(e))

        # create new revision from memory
        memctx = patch.makememctx(repo, (pctx.node(), None),
                                    opts['message'],
                                    opts.get('user'),
                                    opts.get('date'),
                                    repo[None].branch(), 
                                    files,
                                    store,
                                    editor=None)
        newrev = memctx.commit()
    finally:
        store.close()

    # move working directory to new revision
    if newrev:
        wlock = repo.wlock()
        try:
            repo.setparents(newrev)
            ctx = repo[newrev]
            repo.dirstate.rebuild(ctx.node(), ctx.manifest())
            return 0
        finally:
            wlock.release()
    return 1

# We're not using Mercurial's extension loader (so partialcommit will not
# show up in the list of extensions on traceback), so we must protect ourselves
# from multiple registrations

registered = False
def uisetup(ui):
    'Replace commit with a decorator to provide --partials option'
    if registered:
        return
    entry = extensions.wrapcommand(commands.table, 'commit', partialcommit)
    entry[1].append(('', 'partials', [],
                     _("selected patch chunks (internal use only)")))
    registered = True
