"""
taglistdialog.py - dialog for TortoiseHg to display repository tags

 Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>

This software may be used and distributed according to the terms
of the GNU General Public License, incorporated herein by reference.
"""

from listdialog import ListsDialog
from mercurial import hg, repo, ui, cmdutil, util, node
import thgutil

def get_tag_list(path):
    root = thgutil.find_root(path)
    u = ui.ui()
    try:
        repo = hg.repository(u, path=root)
    except repo.RepoError:
        return None

    l = repo.tagslist()
    l.reverse()
    hexfunc = node.hex
    taglist = []
    for t, n in l:
        try:
            hn = hexfunc(n)
            r, c = repo.changelog.rev(n), hexfunc(n)
        except revlog.LookupError:
            r, c = "?", hn

        taglist.append((t, r, c))

    return taglist

headings = ['Name', 'Revision', 'Changeset']

class TagsDialog(ListsDialog):
    def __init__(self, path):
        taglist = get_tag_list(path)
        title = 'Hg tags - %s' % thgutil.find_root(path)
        ListsDialog.__init__(self, title, taglist, headings, resizable=True)

    # support dialog app
    def PreDoModal(self):
        pass

def test(path):
    dlg = TagsDialog(path)
    dlg.CreateWindow()
    
if __name__=='__main__':
    test("c:\hg\h1")
    