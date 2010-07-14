# Copyright (c) 2003-2010 LOGILAB S.A. (Paris, FRANCE).
# http://www.logilab.fr/ -- mailto:contact@logilab.fr
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
"""
help messages for hgview
"""

help_msg = """
hgview: a visual hg log viewer
==============================

This command will launch the hgview log navigator, allowing to
visually browse in the hg graph log, search in logs, and display diff
between arbitrary revisions of a file, with simple support for mq and
bigfile extensions.

If a filename is given, launch the filelog diff viewer for this file, 
and with the '-n' option, launch the filelog navigator for the file.

With the '-r' option, launch the manifest viewer for the given revision.

Revlog graph
------------

The main revision graph display the repository history as a graph,
sorted by revision number.

The color of the node of each revision depends on the named branch the
revision belongs to.

The color of the links (between nodes) is randomly chosen.

The position of the working directory is marked on the graph using a
small sunny icon as node marker. If the working directory has local
modifications, a *virtual* is added in the graph with a special sign
icon (with no revision number). Modified, added and removed files are
listed and browsable as a normal changeset node.

Note that if the working directoy is in merge state, there will be 2
revisions marked as modified in the graph (since the working directory
is then a son of both the merged nodes).

mq support
~~~~~~~~~~

There is a simple support for the mq extension. Applied patches are
seen in the revlog graph with a special arrow icon. Unapplied patches
are *not* in the revlog graph (since they are not mercurial
changesets).

When the currently selected revision is an applied patch, the revision
metadata display (see below) area point this by showing an additional
line with coloured background listing all available patches (applied
or not, so if you cannot see the content of an unapplied patch, you
are aware there are unapplied patches, as long as there is at leat one
applied patch). Current patch is displayed using bold font; unapplied
patches are displayed in italic.


Revision metadata display
-------------------------

The area where current revision's metadata is displayed
(description, parents revisions, etc.) may contain two kinds of hyperlink:

- when the hyperlink is the **changeset ID**, it allows you to
  directly go to the given revision,
  
- when the hyperlink is the **revision number** (on merge nodes only),
  it means that you can change the other revision used to comput
  the diff. This allows you to compare the merged node with each
  of its parents, or even with the common ancestor of these 2
  nodes.


Revision's modified file list
-----------------------------

The file list diplay the list of modified files. The diff
displayed is the one of the selected file, between the selected
revision and its parent revision.

On a merge node, by default, only files which are different from
both its parents are listed here. However, you can display the
list of all modified files by double-clickig the file list column
header.


Quickbars
---------

Quickbars are tollbar that appear when asked for by hitting it's
keybord shortcut. Only one quickbar can be displayed at a time.

When a quickbar is visible, hitting the Esc key make it disappear.

The goto quickbar
~~~~~~~~~~~~~~~~~

This toolbar appears when hitting Ctrl+G. It allows you to jump to a
given revision. The destination revision can be entered by:

- it's revision number (negative values allowed, count from tip)  
- it's changeset ID (short or long)
- a tag name (with completion)
- a branch name
- an empty string; means "goto current working directory"

The search quickbar
~~~~~~~~~~~~~~~~~~~

This toolbar appears when hitting Ctrl+F or / (if not in goto toolbar).

It allows you to type a string to be searched for:

- in the currently displayed revision commit message (with highlight-as-you-type)
- in the currently displayed file or diff (with highlight-as-you-type)

Hitting the "Search next" button starts a background task for searching among the whole
revision log, starting from the current position (selected revision
and file).


Keyboard shortcuts
------------------

**Up/Down**
  go to next/previous revision

**MidButton**
  go to the common ancestor of the clicked revision and the currently selected one


**Left/Right**
  display previous/next files of the current changeset
  
**Ctrl+F** or **/**
  display the search 'quickbar'

**Ctrl+G**
  display the goto 'quickbar'

**Esc**
  exit or hide the visible 'quickbar' 

**Enter**
  run the diff viewer for the currently selected file (display diff
  between revisions)

**Alt+Enter**
  run the filelog navigator

**Shift+Enter**
  run the manifest viewer for the displayed revision
  
**Ctrl+R**
  reread repo; note that by default, repo will be automatically
  reloaded if it is modified (due to a commit, a pull, etc.)
  
**Alt+Up/Down**
  display previous/next diff block

**Alt+Left/Right**
  go to previous/next visited revision (in navigation history)
  
**Backspace**
  set current revision the current start revision (hide any revision above it)
 
**Shit+Backspace**
  clear the start revision value
 

    """

def get_options_helpmsg(rest=False):
    """display hgview full list of configuration options
    """
    from config import get_option_descriptions
    options = get_option_descriptions(rest)
    msg = """
Configuration options
=====================

These should be set under the [hgview] section of the hgrc config file.

"""
    msg += '\n'.join(["- " + v for v in options]) + '\n'
    msg += """
The 'users' config statement should be the path of a file
describing users, like::

    --8<-------------------------------------------
    # file ~/.hgusers
    id=david
    alias=david.douard@logilab.fr
    alias=david@logilab.fr
    alias=David Douard <david.douard@logilab.fr>
    color=#FF0000
    id=ludal
    alias=ludovic.aubry@logilab.fr
    alias=ludal@logilab.fr
    alias=Ludovic Aubry <ludovic.aubry@logilab.fr>
    color=#00FF00
    --8<-------------------------------------------
    
This allow to make several 'authors' under the same name, with the
same color, in the graphlog browser.
    """
    return msg

long_help_msg = help_msg + get_options_helpmsg()
