# purge.py - deleted specified files from given repository
#
# Copyright 2010 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os

# Heavily influenced by Mercurial's purge extension

def purge(repo, files):
    directories = set()
    failures = []

    def remove(remove_func, name):
        try:
            directories.add(os.path.dirname(name) + '/')
            remove_func(repo.wjoin(name))
        except EnvironmentError:
            failures.append(name)

    def removefile(path):
        try:
            os.remove(path)
        except OSError:
            # read-only files cannot be unlinked under Windows
            s = os.stat(path)
            if (s.st_mode & stat.S_IWRITE) != 0:
                raise
            os.chmod(path, stat.S_IMODE(s.st_mode) | stat.S_IWRITE)
            os.remove(path)

    for f in sorted(files):
        remove(removefile, f)

    dirs = list(directories)
    for f in sorted(dirs, reverse=True):
        if not os.listdir(repo.wjoin(f)):
            remove(os.rmdir, f)

    return failures
