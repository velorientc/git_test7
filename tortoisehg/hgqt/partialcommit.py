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
from mercurial import error, bookmarks, util
from mercurial import merge as mergemod

#
# Note all the translatable strings in this file are copies of Mercurial
# strings which are translated by Mercurial's i18n module.
#

def makememctx(repo, parents, text, user, date, extra, files, store):
    def getfilectx(repo, memctx, path):
        if path in store.data or path in store.files:
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
    # opts['message'] is mandatory. --addremove is ignored
    # partial selection patch will only affect modified (M) files.  All adds
    # and removes and non-partial modifications are handled via wctx.
    if 'partials' not in opts:
        return orig(ui, repo, *pats, **opts)

    def fail(f, msg):
        raise util.Abort('%s: %s' % (f, msg))

    if opts.get('subrepos'):
        # Let --subrepos on the command line override config setting.
        repo.ui.setconfig('ui', 'commitsubrepos', True)

    force = opts.get('force')
    date = opts.get('date')
    if date:
        opts['date'] = util.parsedate(date)

    wlock = repo.wlock()
    try:
        wctx = repo[None]
        merge = len(wctx.parents()) > 1

        extra = {'branch': encoding.fromlocal(wctx.branch())}
        if opts.get('close_branch'):
            if repo['.'].node() not in repo.branchheads():
                # The topo heads set is included in the branch heads set of the
                # current branch, so it's sufficient to test branchheads
                raise util.Abort(_('can only close branch heads'))
            extra['close'] = 1

        match = scmutil.match(wctx, pats, opts)
        if not force:
            vdirs = []
            match.dir = vdirs.append
            match.bad = fail

        if (not force and merge and match and
            (match.files() or match.anypats())):
            raise util.Abort(_('cannot partially commit a merge '
                               '(do not specify files or patterns)'))

        changes = repo.status(match=match, clean=force)
        if force:
            changes[0].extend(changes[6]) # mq may commit unchanged files

        # check subrepos
        subs = []
        commitsubs = set()
        newstate = wctx.substate.copy()
        # only manage subrepos and .hgsubstate if .hgsub is present
        if '.hgsub' in wctx:
            # we'll decide whether to track this ourselves, thanks
            if '.hgsubstate' in changes[0]:
                changes[0].remove('.hgsubstate')
            if '.hgsubstate' in changes[2]:
                changes[2].remove('.hgsubstate')

            # compare current state to last committed state
            # build new substate based on last committed state
            oldstate = wctx.p1().substate
            for s in sorted(newstate.keys()):
                if not match(s):
                    # ignore working copy, use old state if present
                    if s in oldstate:
                        newstate[s] = oldstate[s]
                        continue
                    if not force:
                        raise util.Abort(
                            _("commit with new subrepo %s excluded") % s)
                if wctx.sub(s).dirty(True):
                    if not repo.ui.configbool('ui', 'commitsubrepos'):
                        raise util.Abort(
                            _("uncommitted changes in subrepo %s") % s,
                            hint=_("use --subrepos for recursive commit"))
                    subs.append(s)
                    commitsubs.add(s)
                else:
                    bs = wctx.sub(s).basestate()
                    newstate[s] = (newstate[s][0], bs, newstate[s][2])
                    if oldstate.get(s, (None, None, None))[1] != bs:
                        subs.append(s)

            # check for removed subrepos
            for p in wctx.parents():
                r = [s for s in p.substate if s not in newstate]
                subs += [s for s in r if match(s)]
            if subs:
                if (not match('.hgsub') and
                    '.hgsub' in (wctx.modified() + wctx.added())):
                    raise util.Abort(
                        _("can't commit subrepos without .hgsub"))
                changes[0].insert(0, '.hgsubstate')

        elif '.hgsub' in changes[2]:
            # clean up .hgsubstate when .hgsub is removed
            if ('.hgsubstate' in wctx and
                '.hgsubstate' not in changes[0] + changes[1] + changes[2]):
                changes[2].insert(0, '.hgsubstate')

        # make sure all explicit patterns are matched
        if not force and match.files():
            matched = set(changes[0] + changes[1] + changes[2])

            for f in match.files():
                f = repo.dirstate.normalize(f)
                if f == '.' or f in matched or f in wctx.substate:
                    continue
                if f in changes[3]: # missing
                    fail(f, _('file not found!'))
                if f in vdirs: # visited directory
                    d = f + '/'
                    for mf in matched:
                        if mf.startswith(d):
                            break
                    else:
                        fail(f, _("no match under directory!"))
                elif f not in repo.dirstate:
                    fail(f, _("file not tracked!"))

        if (not force and not extra.get("close") and not merge
            and not (changes[0] or changes[1] or changes[2])
            and wctx.branch() == wctx.p1().branch()):
            return None

        if merge and changes[3]:
            raise util.Abort(_("cannot commit merge with missing files"))

        ms = mergemod.mergestate(repo)
        for f in changes[0]:
            if f in ms and ms[f] == 'u':
                raise util.Abort(_("unresolved merge conflicts "
                                   "(see hg help resolve)"))

        # commit subs and write new state
        if subs:
            for s in sorted(commitsubs):
                sub = wctx.sub(s)
                repo.ui.status(_('committing subrepository %s\n') %
                    subrepo.subrelpath(sub))
                sr = sub.commit(opts['message'], opts.get('user'), opts.get('date'))
                newstate[s] = (newstate[s][0], sr)
            subrepo.writestate(repo, newstate)

        p1, p2 = repo.dirstate.parents()
        hookp1, hookp2 = hex(p1), (p2 != nullid and hex(p2) or '')
        repo.hook("precommit", throw=True, parent1=hookp1, parent2=hookp2)

        newrev = None
        patchfile = opts['partials']
        fp = open(patchfile, 'rb')
        store = patch.filestore()
        try:
            # patch files in tmp directory
            try:
                patch.patchrepo(ui, repo, repo['.'], store, fp, 1, None)
            except patch.PatchError, e:
                raise util.Abort(str(e))

            # create memctx, use to create a new changeset
            matched = changes[0] + changes[1] + changes[2]
            memctx = makememctx(repo, (p1, p2), opts['message'],
                                opts.get('user'), opts.get('date'), extra,
                                matched, store)
            newrev = memctx.commit()
        finally:
            store.close()
            fp.close()
            os.unlink(patchfile)

        # move working directory to new revision
        if newrev:
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
