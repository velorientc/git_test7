# textview.py - TextView/TextBuffer with undo/redo functionality
#
# Copyright 2009 Florian Heinle
# Copyright 2010 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import gtk
import gobject

from tortoisehg.hgtk import gtklib

class UndoableInsert(object):
    """something that has been inserted into our textbuffer"""
    def __init__(self, text_iter, text, length):
        self.time = gobject.get_current_time()
        self.offset = text_iter.get_offset()
        self.text = text
        self.length = length
        if self.length > 1 or self.text in ('\r', '\n', ' '):
            self.mergeable = False
        else:
            self.mergeable = True

class UndoableDelete(object):
    """something that has ben deleted from our textbuffer"""
    def __init__(self, text_buffer, start_iter, end_iter):
        self.time = gobject.get_current_time()
        self.text = text_buffer.get_text(start_iter, end_iter)
        self.start = start_iter.get_offset()
        self.end = end_iter.get_offset()
        # need to find out if backspace or delete key has been used
        # so we don't mess up during redo
        insert_iter = text_buffer.get_iter_at_mark(text_buffer.get_insert())
        if insert_iter.get_offset() <= self.start:
            self.delete_key_used = True
        else:
            self.delete_key_used = False
        if self.end - self.start > 1 or self.text in ('\r', '\n', ' '):
            self.mergeable = False
        else:
            self.mergeable = True

class UndoableReplace(object):
    def __init__(self, first, second):
        self.first = first
        self.second = second

class UndoableTextBuffer(gtk.TextBuffer):
    """text buffer with added undo capabilities

    designed as a drop-in replacement for gtksourceview,
    at least as far as undo is concerned"""

    def __init__(self):
        """
        we'll need empty stacks for undo and some state keeping
        """
        gtk.TextBuffer.__init__(self)
        self.undo_stack = []
        self.redo_stack = []
        self.not_undoable_action = False
        self.undo_in_progress = False
        self.connect('insert-text', self.on_insert_text)
        self.connect('delete-range', self.on_delete_range)

    @property
    def can_undo(self):
        return bool(self.undo_stack)

    @property
    def can_redo(self):
        return bool(self.redo_stack)

    def on_insert_text(self, textbuffer, text_iter, text, length):
        def can_be_merged(prev, cur):
            """see if we can merge multiple inserts here

            will try to merge words or whitespace
            can't merge if prev is UndoableDelete
            can't merge if prev and cur are not mergeable in the first place
            can't merge when user set the input bar somewhere else
            can't merge across word boundaries"""
            WHITESPACE = (' ', '\t')
            if isinstance(prev, UndoableReplace):
                prev = prev.second
            if isinstance(prev, UndoableDelete):
                return False
            elif not cur.mergeable or not prev.mergeable:
                return False
            elif cur.offset != (prev.offset + prev.length):
                return False
            elif cur.text in WHITESPACE and not prev.text in WHITESPACE:
                return False
            elif prev.text in WHITESPACE and not cur.text in WHITESPACE:
                return False
            return True
        def can_be_replaced(prev, cur):
            return isinstance(prev, UndoableDelete) and prev.time == cur.time

        if not self.undo_in_progress:
            self.redo_stack = []
        if self.not_undoable_action:
            return
        undo_action = UndoableInsert(text_iter, text, length)
        try:
            prev_action = self.undo_stack.pop()
        except IndexError:
            self.undo_stack.append(undo_action)
            return
        if can_be_replaced(prev_action, undo_action):
            undo_action = UndoableReplace(prev_action, undo_action)
        elif can_be_merged(prev_action, undo_action):
            if isinstance(prev_action, UndoableReplace):
                merge_action = prev_action.second
            else:
                merge_action = prev_action
            merge_action.length += undo_action.length
            merge_action.text += undo_action.text
            undo_action = prev_action
        else:
            self.undo_stack.append(prev_action)
        self.undo_stack.append(undo_action)

    def on_delete_range(self, text_buffer, start_iter, end_iter):
        def can_be_merged(prev, cur):
            """see if we can merge multiple deletions here

            will try to merge words or whitespace
            can't merge if prev is UndoableInsert
            can't merge if prev and cur are not mergeable in the first place
            can't merge if delete and backspace key were both used
            can't merge across word boundaries"""

            WHITESPACE = (' ', '\t')
            if isinstance(prev, UndoableReplace):
                prev = prev.second
            if isinstance(prev, UndoableInsert):
                return False
            elif not cur.mergeable or not prev.mergeable:
                return False
            elif prev.delete_key_used != cur.delete_key_used:
                return False
            elif prev.start != cur.start and prev.start != cur.end:
                return False
            elif cur.text not in WHITESPACE and \
               prev.text in WHITESPACE:
                return False
            elif cur.text in WHITESPACE and \
               prev.text not in WHITESPACE:
                return False
            return True
        def can_be_replaced(prev, cur):
            return isinstance(prev, UndoableInsert) and prev.time == cur.time

        if not self.undo_in_progress:
            self.redo_stack = []
        if self.not_undoable_action:
            return
        undo_action = UndoableDelete(text_buffer, start_iter, end_iter)
        try:
            prev_action = self.undo_stack.pop()
        except IndexError:
            self.undo_stack.append(undo_action)
            return
        if can_be_replaced(prev_action, undo_action):
            undo_action = UndoableReplace(prev_action, undo_action)
        elif can_be_merged(prev_action, undo_action):
            if isinstance(prev_action, UndoableReplace):
                merge_action = prev_action.second
            else:
                merge_action = prev_action
            if merge_action.start == undo_action.start: # delete key used
                merge_action.text += undo_action.text
                merge_action.end += (undo_action.end - undo_action.start)
            else: # Backspace used
                merge_action.text = '%s%s' % (undo_action.text,
                                              merge_action.text)
                merge_action.start = undo_action.start
            undo_action = prev_action
        else:
            self.undo_stack.append(prev_action)
        self.undo_stack.append(undo_action)

    def begin_not_undoable_action(self):
        """don't record the next actions

        toggles self.not_undoable_action"""
        self.not_undoable_action = True

    def end_not_undoable_action(self):
        """record next actions

        toggles self.not_undoable_action"""
        self.not_undoable_action = False

    def undo(self):
        """undo inserts or deletions

        undone actions are being moved to redo stack"""
        if not self.undo_stack:
            return
        self.begin_not_undoable_action()
        self.undo_in_progress = True
        undo_action = self.undo_stack.pop()
        self.redo_stack.append(undo_action)
        def do_insert(action):
            start = self.get_iter_at_offset(action.offset)
            stop = self.get_iter_at_offset(
                action.offset + action.length
            )
            self.delete(start, stop)
            self.place_cursor(start)
        def do_delete(action):
            start = self.get_iter_at_offset(action.start)
            self.insert(start, action.text)
            stop = self.get_iter_at_offset(action.end)
            if action.delete_key_used:
                self.place_cursor(start)
            else:
                self.place_cursor(stop)
        def do(action):
            if isinstance(action, UndoableInsert):
                do_insert(action)
            elif isinstance(action, UndoableDelete):
                do_delete(action)
        if isinstance(undo_action, UndoableReplace):
            do(undo_action.second)
            do(undo_action.first)
        else:
            do(undo_action)
        self.end_not_undoable_action()
        self.undo_in_progress = False

    def redo(self):
        """redo inserts or deletions

        redone actions are moved to undo stack"""
        if not self.redo_stack:
            return
        self.begin_not_undoable_action()
        self.undo_in_progress = True
        redo_action = self.redo_stack.pop()
        self.undo_stack.append(redo_action)
        def do_insert(action):
            start = self.get_iter_at_offset(action.offset)
            self.insert(start, action.text)
            new_cursor_pos = self.get_iter_at_offset(
                action.offset + action.length
            )
            self.place_cursor(new_cursor_pos)
        def do_delete(action):
            start = self.get_iter_at_offset(action.start)
            stop = self.get_iter_at_offset(action.end)
            self.delete(start, stop)
            self.place_cursor(start)
        def do(action):
            if isinstance(action, UndoableInsert):
                do_insert(action)
            elif isinstance(action, UndoableDelete):
                do_delete(action)
        if isinstance(redo_action, UndoableReplace):
            do(redo_action.first)
            do(redo_action.second)
        else:
            do(redo_action)
        self.end_not_undoable_action()
        self.undo_in_progress = False

class UndoableTextView(gtk.TextView):
    def __init__(self, buffer=None, accelgroup=None):
        if buffer is None:
            buffer = UndoableTextBuffer()
        gtk.TextView.__init__(self, buffer)

        if accelgroup:
            mod = gtklib.get_thg_modifier()
            key, modifier = gtk.accelerator_parse(mod+'z')
            self.add_accelerator('thg-undo', accelgroup, key,
                                 modifier, gtk.ACCEL_VISIBLE)
            def do_undo(view):
                buffer = self.get_buffer()
                if hasattr(buffer, 'undo'):
                    buffer.undo()
            self.connect('thg-undo', do_undo)

            key, modifier = gtk.accelerator_parse(mod+'y')
            self.add_accelerator('thg-redo', accelgroup, key,
                                 modifier, gtk.ACCEL_VISIBLE)
            def do_redo(view):
                buffer = self.get_buffer()
                if hasattr(buffer, 'redo'):
                    buffer.redo()
            self.connect('thg-redo', do_redo)
