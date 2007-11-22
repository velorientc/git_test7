#
# revision dialog for TortoiseHg dialogs
#
# Copyright (C) 2007 TK Soh <teekaysoh@gmail.com>
#

try:
    import pygtk
    pygtk.require("2.0")
except:
    pass

import gtk
import gobject
import pango
from mercurial import hg, ui, cmdutil, util
from mercurial.i18n import _
from mercurial.node import *
from dialog import error_dialog, question_dialog
from revtree import RevisionTree

class RevisionDialog(gtk.Dialog):
    def __init__(self, root=''):
        """ Initialize the Dialog. """        
        gtk.Dialog.__init__(self, title="TortoiseHg Revisions - %s" % root,
                                  parent=None,
                                  flags=0,
                                  buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))

        self.root = root

        self._button_refresh = gtk.Button(_("Refresh"))
        self._button_refresh.connect('clicked', self._button_refresh_clicked)
        self._button_refresh.set_flags(gtk.CAN_DEFAULT)
        self.action_area.pack_end(self._button_refresh)

        # Create a new notebook, place the position of the tabs
        self.notebook = notebook = gtk.Notebook()
        notebook.set_tab_pos(gtk.POS_TOP)
        self.vbox.pack_start(notebook)
        notebook.show()
        self.show_tabs = True
        self.show_border = True

        # create pages for each type of revision info
        self.pages = []
        self.tip_tree = self.add_page(notebook, 'Tip')
        self.parents_tree = self.add_page(notebook, 'Parents')
        self.heads_tree = self.add_page(notebook, 'Heads')

        self.vbox.show_all()
        
        # populate revision data
        self._get_revisions()
        
    def add_page(self, notebook, tab):
        self.pages.append(tab)
        
        frame = gtk.Frame()
        frame.set_border_width(10)
        frame.set_size_request(500, 250)
        frame.show()

        tree = RevisionTree()
        frame.add(tree)

        label = gtk.Label(tab)
        notebook.append_page(frame, label)

        return tree
    
    def select_page(self, name):
        try:
            # do case-insentive search on page name
            lpages = [x.lower() for x in self.pages]
            page_num = lpages.index(name.lower())
            
            # show select page
            self.notebook.set_current_page(page_num)
        except:
            pass
            
    def _button_refresh_clicked(self, button):
        """ Refresh button clicked handler. """
        self._get_revisions()
        print "refreshed"
        
    def _get_revisions(self):
        """ retrieve repo revisions """
        u = ui.ui()
        try:
            repo = hg.repository(u, path=self.root)
        except hg.RepoError:
            return None
        self.repo = repo
        
        text = self.tip(repo)
        self.tip_tree.set_history(_(text))
        text = self.parents(repo)
        self.parents_tree.set_history(_(text))
        text = self.heads(repo)
        self.heads_tree.set_history(_(text))
        
    def tip(self, repo):
        """ Show the tip revision """
        repo.ui.pushbuffer()
        cmdutil.show_changeset(repo.ui, repo, {}).show(nullrev+repo.changelog.count())
        text = repo.ui.popbuffer()
        return text
        
    def parents(self, repo):
        """ Show the parent revisions """
        p = repo.dirstate.parents()
        repo.ui.pushbuffer()
        displayer = cmdutil.show_changeset(repo.ui, repo, {})
        for n in p:
            if n != nullid:
                displayer.show(changenode=n)
        text = repo.ui.popbuffer()
        return text
        
    def heads(self, repo):
        """ Show the head revisions """
        heads = repo.heads()
        repo.ui.pushbuffer()
        displayer = cmdutil.show_changeset(repo.ui, repo, {})
        for n in heads:
            displayer.show(changenode=n)
        text = repo.ui.popbuffer()
        return text
        
def run(root='', page=None):
    dlg = RevisionDialog(root=root)
    if page:
        dlg.select_page(page)
    dlg.run()

if __name__ == "__main__":
    import sys
    run()