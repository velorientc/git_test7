# gdialog.py - base dialog for gtools
#
# Copyright 2007 Brad Schick, brad at gmail . com
# Copyright 2008 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import os
import threading
import cStringIO
import sys
import shutil
import tempfile
import gtk
import atexit

from mercurial import cmdutil, util, ui, hg, commands

from tortoisehg.util.i18n import _
from tortoisehg.util import settings, hglib, paths

from tortoisehg.hgtk import gtklib

class SimpleMessage(gtklib.MessageDialog):
    def run(self):
        response = gtklib.MessageDialog.run(self)
        self.destroy()
        return response


class Prompt(SimpleMessage):
    def __init__(self, title, message, parent, type=gtk.MESSAGE_INFO):
        SimpleMessage.__init__(self, parent, gtk.DIALOG_MODAL,
                type, gtk.BUTTONS_CLOSE)
        self.set_title('TortoiseHg')
        self.set_markup(gtklib.markup(hglib.toutf(title), weight='bold'))
        self.format_secondary_text(hglib.toutf(message))
        mod = gtklib.get_thg_modifier()
        key, modifier = gtk.accelerator_parse(mod+'Return')
        accel_group = gtk.AccelGroup()
        self.add_accel_group(accel_group)
        buttons = self.get_children()[0].get_children()[1].get_children()
        buttons[0].add_accelerator('clicked', accel_group, key,
                modifier, gtk.ACCEL_VISIBLE)

class CustomPrompt(gtk.MessageDialog):
    ''' Custom prompt dialog.  Provide a list of choices with ampersands
    to delineate response given for each choice (and keyboard
    accelerator). Default must be the index of one of the choice responses.
    '''
    # ret = CustomPrompt('Title', 'Message', self, ('&Yes', 'N&o'), 1).run()
    # ret will be (gtk.RESPONSE_DELETE_EVENT, 0 (for yes), or 1 (for no)
    def __init__(self, title, message, parent, choices, default=None, esc=None):
        gtk.MessageDialog.__init__(self, parent, gtk.DIALOG_MODAL,
                gtk.MESSAGE_QUESTION)
        self.set_title(hglib.toutf(title))
        self.format_secondary_markup(gtklib.markup(hglib.toutf(message),
                                     weight='bold'))
        accel_group = gtk.AccelGroup()
        self.add_accel_group(accel_group)
        for i, s in enumerate(choices):
            button = self.add_button(s.replace('&', '_'), i)
            try:
                char = s[s.index('&')+1].lower()
                button.add_accelerator('clicked', accel_group, ord(char),
                                       0, gtk.ACCEL_VISIBLE)
            except ValueError:
                pass
        if default:
            self.set_default_response(default)
        self.esc = esc

    def run(self):
        response = gtklib.MessageDialog.run(self)
        if response == gtk.RESPONSE_DELETE_EVENT and self.esc != None:
            response = self.esc
        self.destroy()
        return response

class Confirm(SimpleMessage):
    """Dialog returns gtk.RESPONSE_YES or gtk.RESPONSE_NO
    """
    def __init__(self, title, files, parent, primary):
        SimpleMessage.__init__(self, parent, gtk.DIALOG_MODAL,
                gtk.MESSAGE_QUESTION, gtk.BUTTONS_YES_NO)
        self.set_title(hglib.toutf(title))
        self.set_markup(gtklib.markup(hglib.toutf(primary), weight='bold'))
        message = ''
        for i, f in enumerate(files):
            message += '   ' + f + '\n'
            if i == 9:
                message += '   ...\n'
                break
        self.format_secondary_text(hglib.toutf(message))
        accel_group = gtk.AccelGroup()
        self.add_accel_group(accel_group)
        buttons = self.get_children()[0].get_children()[1].get_children()
        buttons[1].add_accelerator("clicked", accel_group, ord("y"),
                              0, gtk.ACCEL_VISIBLE)
        buttons[0].add_accelerator("clicked", accel_group, ord("n"),
                              0, gtk.ACCEL_VISIBLE)


class GDialog(gtk.Window):
    """GTK+ based dialog for displaying mercurial information

    The following methods are meant to be overridden by subclasses. At this
    point GCommit is really the only intended subclass.

        parse_opts(self)
        get_title(self)
        get_minsize(self)
        get_defsize(self)
        get_tbbuttons(self)
        get_menu_list(self)
        get_help_url(self)
        get_default_setting(self)
        get_body(self)
        get_extras(self)
        prepare_display(self)
        should_live(self, widget, event)
        save_settings(self)
        load_settings(self, settings)
    """

    # "Constants"
    def __init__(self, ui, repo, cwd, pats, opts):
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        self.cwd = cwd or os.getcwd()
        self.ui = ui
        self.ui.setconfig('ui', 'interactive', 'off')
        if repo:
            self.repo = repo
        else:
            root = paths.find_root()
            if root:
                self.repo = hg.repository(ui, path=root)
            else:
                self.repo = None
        self.pats = pats
        self.opts = opts
        self.tmproot = None
        self.toolbuttons = {}
        self.menuitems = {}
        self.settings = settings.Settings(self.__class__.__name__)
        self.init()

    def refreshui(self):
        self.ui = ui.ui()
        self.ui.setconfig('ui', 'interactive', 'off')
        if self.repo:
            self.repo = hg.repository(self.ui, path=self.repo.root)

    ### Following methods are meant to be overridden by subclasses ###

    def init(self):
        pass

    def parse_opts(self):
        pass


    def get_title(self):
        return ''

    def get_icon(self):
        return ''

    def get_minsize(self):
        return (395, 200)


    def get_defsize(self):
        return self._setting_defsize


    def get_tbbuttons(self):
        return []


    def get_menu_list(self):
        return None


    def get_help_url(self):
        return None


    def get_default_setting(self):
        return None


    def get_body(self):
        return None


    def get_extras(self):
        return None


    def prepare_display(self):
        pass


    def should_live(self, widget=None, event=None):
        self._destroying(widget)
        return False


    def save_settings(self):
        settings = {}
        rect = self.get_allocation()
        if self.ismaximized or self.isiconified:
            settings['gdialog-rect'] = self._setting_defsize
            settings['gdialog-pos'] = self._setting_winpos
        else:
            settings['gdialog-rect'] = (rect.width, rect.height)
            settings['gdialog-pos'] = self.lastpos
        settings['gdialog-ismax'] = self.ismaximized
        return settings


    def load_settings(self, settings):
        self._setting_defsize = (678, 585)
        self._setting_winpos = (0, 0)
        self._setting_wasmax = False
        try:
            self._setting_defsize = settings['gdialog-rect']
            self._setting_winpos = settings['gdialog-pos']
            self._setting_wasmax = settings['gdialog-ismax']
        except KeyError:
            pass


    def show_toolbar_on_start(self):
        return True

    ### End of overridable methods ###

    def display(self, opengui=True):
        self._parse_config()
        self._load_settings()
        if opengui:
            self._setup_gtk()
            self._parse_opts()
            self.prepare_display()
            self.show_all()
        else:
            self._parse_opts()
            self.tooltips = gtk.Tooltips()


    def test_opt(self, opt):
        return self.opts.get(opt, False)

    def _parse_config(self):
        # defaults
        self.fontcomment = 'monospace 10'
        self.fontdiff = 'monospace 10'
        self.fontlist = 'Sans 9'
        self.diffbottom = ''

        for attr, setting in self.ui.configitems('gtools'):
            if setting : setattr(self, attr, setting)

        if not self.diffbottom:
            self.diffbottom = False
        elif self.diffbottom.lower() == 'false' or self.diffbottom == '0':
            self.diffbottom = False
        else:
            self.diffbottom = True


    def _parse_opts(self):
        # Remove dry_run since Hg only honors it for certain commands
        self.opts['dry_run'] = False
        self.opts['force_editor'] = False
        self.parse_opts()


    def merge_opts(self, defaults, mergelist=()):
        """Merge default options with the specified local options and globals.
        Results is defaults + merglist + globals
        """
        newopts = {}
        for hgopt in defaults:
            newopts[hgopt[1].replace('-', '_')] = hgopt[2]
        for mergeopt in mergelist:
            newopts[mergeopt] = self.opts[mergeopt]
        newopts.update(self.global_opts())
        return newopts


    def global_opts(self):
        globalopts = {}
        hgglobals = [opt[1] for opt in commands.globalopts if opt[1] != 'help']
        hgglobals = [f.replace('-', '_') for f in hgglobals]
        for key in self.opts:
            if key in  hgglobals :
                globalopts[key] = self.opts[key]
        return globalopts


    def count_revs(self):
        cnt = 0
        if self.test_opt('rev'):
            for rev in self.opts['rev']:
                cnt += len(rev.split(cmdutil.revrangesep, 1))
        return cnt


    def make_toolbutton(self, stock, label, handler, userdata=None,
                menu=None, tip=None, toggle=False, icon=None, name=None):
        if menu:
            tbutton = gtk.MenuToolButton(stock)
            tbutton.set_menu(menu)
        elif toggle:
            tbutton = gtk.ToggleToolButton(stock)
        else:
            tbutton = gtk.ToolButton(stock)

        if tip:
            tbutton.set_tooltip(self.tooltips, tip)
        if icon:
            path = paths.get_tortoise_icon(icon)
            if path:
                image = gtk.Image()
                image.set_from_file(path)
                tbutton.set_icon_widget(image)
        tbutton.set_use_underline(True)
        tbutton.set_label(label)
        tbutton.connect('clicked', handler, userdata)
        if name:
            self.toolbuttons[name] = tbutton
        return tbutton

    def get_toolbutton(self, name):
        return self.toolbuttons[name]

    def get_menuitem(self, name):
        return self.menuitems[name]

    def get_widgets(self, name):
        widgets = []
        widgets.append(self.toolbuttons.get(name))
        widgets.append(self.menuitems.get(name))
        return widgets

    def cmd_set_sensitive(self, name, sensitive):
        for w in self.get_widgets(name):
            if w:
                w.set_sensitive(sensitive)

    def cmd_set_active(self, name, active):
        for w in self.get_widgets(name):
            if w and hasattr(w, 'set_active'):
                w.set_active(active)

    def cmd_get_active(self, name, fallback=None):
        prev = None
        for w in self.get_widgets(name):
            if w and hasattr(w, 'set_active'):
                active = w.get_active()
                if prev is not None and prev != active:
                    return fallback
                prev = active
        return prev

    def cmd_handler_block_by_func(self, name, func):
        for w in self.get_widgets(name):
            if w:
                w.handler_block_by_func(func)

    def cmd_handler_unblock_by_func(self, name, func):
        for w in self.get_widgets(name):
            if w:
                w.handler_unblock_by_func(func)

    def get_reponame(self):
        return hglib.get_reponame(self.repo)

    def helpcontents(self, item):
        'User selected Help->Contents from menu bar'
        url = self.get_help_url()
        if not url:
            return
        if not url.startswith('http'):
            url = 'http://tortoisehg.org/manual/0.9/' + url
        from tortoisehg.hgtk import about
        about.browse_url(url)

    def launch(self, item, app):
        import sys
        # Spawn background process and exit
        if hasattr(sys, "frozen"):
            args = [sys.argv[0], app]
        else:
            args = [sys.executable] + [sys.argv[0], app]
        if app.endswith('config') and self.get_default_setting():
            args += ['--focus', self.get_default_setting()]
        if os.name == 'nt':
            args = ['"%s"' % arg for arg in args]
        oldcwd = os.getcwd()
        root = paths.find_root(oldcwd)
        try:
            os.chdir(root)
            os.spawnv(os.P_NOWAIT, sys.executable, args)
        finally:
            os.chdir(oldcwd)

    def windowstate(self, window, event):
        if event.changed_mask & gtk.gdk.WINDOW_STATE_MAXIMIZED:
            if event.new_window_state & gtk.gdk.WINDOW_STATE_MAXIMIZED:
                self.ismaximized = True
            else:
                self.ismaximized = False
        if event.changed_mask & gtk.gdk.WINDOW_STATE_ICONIFIED:
            if event.new_window_state & gtk.gdk.WINDOW_STATE_ICONIFIED:
                self.isiconified = True
            else:
                self.isiconified = False

    def setfocus(self, window, event):
        self.lastpos = self.get_position()

    def _setup_gtk(self):
        self.set_title(self.get_title())
        gtklib.set_tortoise_icon(self, self.get_icon())
        gtklib.set_tortoise_keys(self)

        self.ismaximized = False
        self.isiconified = False
        self.lastpos = self._setting_winpos
        self.connect('window-state-event', self.windowstate)
        self.connect('set-focus', self.setfocus)

        # Minimum size
        minx, miny = self.get_minsize()
        self.set_size_request(minx, miny)
        # Initial size
        defx, defy = self.get_defsize()
        self.set_default_size(defx, defy)
        if self._setting_wasmax:
            self.maximize()

        # Restore position if it is still on screen
        screen = self.get_screen()
        w, h = screen.get_width(), screen.get_height()
        x, y = self._setting_winpos
        if x >= 0 and x < w and y >= 0 and y < h:
            self.move(x, y)

        self.tooltips = gtk.Tooltips()
        toolbar = gtk.Toolbar()
        tbuttons =  self.get_tbbuttons()
        for tbutton in tbuttons:
            toolbar.insert(tbutton, -1)
        self.toolbar = toolbar

        # Subclass returns the main body
        body = self.get_body()

        # Subclass provides extra stuff in bottom hbox
        extras = self.get_extras()

        menus = self.get_menu_list()
        if menus:
            allmenus = [
          (_('_Tools'),
           [dict(text=_('Repository Explorer'), func=self.launch, args=['log'],
                icon='menulog.ico'),
            dict(text=_('Commit'), func=self.launch, args=['commit'],
                icon='menucommit.ico'),
            dict(text=_('Datamine'), func=self.launch, args=['datamine'],
                icon='menurepobrowse.ico'),
            dict(text=_('Recovery'), func=self.launch, args=['recover'],
                icon='general.ico'),
            dict(text=_('Serve'), func=self.launch, args=['serve'],
                icon='proxy.ico'),
            dict(text=_('Shelve'), func=self.launch, args=['shelve'],
                icon='shelve.ico'),
            dict(text=_('Synchronize'), func=self.launch, args=['synch'],
                icon='menusynch.ico'),
            dict(text=_('Settings'), func=self.launch, args=['repoconfig'],
                icon='settings_repo.ico')])
           ] + menus + [
          (_('_Help'),
           [dict(text=_('Contents'), func=self.helpcontents,
                icon=gtk.STOCK_INFO),
            dict(text=_('About'), func=self.launch, args=['about'],
                icon=gtk.STOCK_ABOUT)])
          ]
            menubar = gtk.MenuBar()
            for title, items in allmenus:
                m_items = gtklib.MenuItems()
                for d in items:
                    text = d['text']
                    name = d.get('name')
                    func = d.get('func')
                    ascheck = d.get('ascheck', False)
                    args = d.get('args', [])
                    icon = d.get('icon')
                    check = d.get('check', False)
                    sensitive = d.get('sensitive', None)
                    if text == '----':
                        item = gtk.SeparatorMenuItem()
                    else:
                        if ascheck:
                            item = gtk.CheckMenuItem(text)
                            item.set_active(check)
                        elif icon:
                            item = gtk.ImageMenuItem(text)
                            if icon.startswith('gtk'):
                                img = gtk.image_new_from_stock(
                                    icon, gtk.ICON_SIZE_MENU)
                            else:
                                img = gtk.Image()
                                ico = paths.get_tortoise_icon(icon)
                                if ico:
                                    try:
                                        width, height = gtk.icon_size_lookup(
                                            gtk.ICON_SIZE_MENU)
                                        pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(
                                            ico, width, height)
                                        img.set_from_pixbuf(pixbuf)
                                    except:
                                        # don't let broken gtk+ to break dialogs
                                        pass
                            item.set_image(img)
                        else:
                            item = gtk.MenuItem(text)
                        if sensitive is not None:
                            item.set_sensitive(sensitive)
                        item.connect('activate', func, *args)
                        if name:
                            self.menuitems[name] = item
                    m_items.append(item)
                item = gtk.MenuItem(title)
                item.set_submenu(m_items.create_menu())
                menubar.append(item)

        vbox = gtk.VBox(False, 0)
        self.add(vbox)
        if menus:
            vbox.pack_start(menubar, False, False, 0)

        self.toolbar_box = gtk.VBox()
        vbox.pack_start(self.toolbar_box, False, False, 0)
        if self.show_toolbar_on_start():
            self._show_toolbar(True)

        vbox.pack_start(body, True, True, 0)
        if extras:
            vbox.pack_end(extras, False, False, 0)

        self.connect('destroy', self._destroying)


    def _show_toolbar(self, show):
        if self.toolbar in self.toolbar_box.get_children():
            self.toolbar.set_property('visible', show)
        elif show:
            self.toolbar_box.pack_start(self.toolbar, False, False, 0)
            self.toolbar.show_all()


    def _destroying(self, gtkobj):
        settings = self.save_settings()
        self.settings.set_value('dialogs', settings)
        self.settings.write()


    def _load_settings(self):
        settings = self.settings.get_value('dialogs', {})
        self.load_settings(settings)


    def _hg_call_wrapper(self, title, command, showoutput=True):
        """Run the specified command and display any resulting aborts,
        messages, and errors
        """
        textout = ''
        saved = sys.stderr
        errors = cStringIO.StringIO()
        try:
            sys.stderr = errors
            self.ui.pushbuffer()
            try:
                command()
            except (util.Abort, IOError, OSError), inst:
                Prompt(title + _(' Aborted'), str(inst), self).run()
                return False, ''
        finally:
            sys.stderr = saved
            textout = self.ui.popbuffer()
            prompttext = ''
            if showoutput:
                prompttext = textout + '\n'
            prompttext += errors.getvalue()
            errors.close()
            if len(prompttext) > 1:
                Prompt(title + _(' Messages and Errors'),
                       prompttext, self).run()

        return True, textout

    def _do_diff(self, canonpats, options):
        from tortoisehg.hgtk import visdiff
        options['canonpats'] = canonpats
        dialog = visdiff.run(self.ui, **options)
        if not dialog:
            return
        dialog.show_all()
        dialog.run()
        dialog.hide()

    def _diff_file(self, stat, file):
        self._do_diff(file and [file] or [], self.opts)

    def _view_files(self, files, otherparent):
        from tortoisehg.hgtk import thgconfig
        def cleanup():
            shutil.rmtree(self.tmproot)

        if not self.tmproot:
            self.tmproot = tempfile.mkdtemp(prefix='gtools.')
            atexit.register(cleanup)

        def snapshot_node(ui, repo, files, node, tmproot):
            '''
            snapshot files as of some revision
            (adapted from Extdiff extension)
            '''
            ctx = repo[node]
            mf = ctx.manifest()
            dirname = os.path.basename(repo.root)
            if dirname == "":
                dirname = "root"
            dirname = '%s.%s' % (dirname, str(ctx))
            base = os.path.join(tmproot, dirname)
            try:
                os.mkdir(base)
            except:
                pass
            ui.note(_('making snapshot of %d files from rev %s\n') %
                    (len(files), str(ctx)))
            for fn in files:
                if not fn in mf:
                    # skipping new file after a merge ?
                    continue
                wfn = util.pconvert(fn)
                ui.note('  %s\n' % wfn)
                dest = os.path.join(base, wfn)
                destdir = os.path.dirname(dest)
                if not os.path.isdir(destdir):
                    os.makedirs(destdir)
                data = repo.wwritedata(wfn, repo.file(wfn).read(mf[wfn]))
                open(dest, 'wb').write(data)
            return dirname

        def doedit():
            pathroot = self.repo.root
            copynode = None
            # if we aren't looking at the wc, copy the node...
            if otherparent:
                copynode = self._node1
            elif self._node2:
                copynode = self._node2

            if copynode:
                pf = [util.pconvert(f) for f in files]
                copydir = snapshot_node(self.ui, self.repo, pf,
                        copynode, self.tmproot)
                pathroot = os.path.join(self.tmproot, copydir)

            paths = ['"'+os.path.join(pathroot, f)+'"' for f in files]
            command = editor + ' ' + ' '.join(paths)
            util.system(command,
                        environ={'HGUSER': self.ui.username()},
                        onerr=self.ui, errprefix=_('edit failed'))

        editor = (self.ui.config('tortoisehg', 'editor') or
                self.ui.config('gtools', 'editor') or
                os.environ.get('HGEDITOR') or
                self.ui.config('ui', 'editor') or
                os.environ.get('EDITOR', 'vi'))
        if os.path.basename(editor) in ('vi', 'vim', 'hgeditor'):
            Prompt(_('No visual editor configured'),
                   _('Please configure a visual editor.'), self).run()
            dlg = thgconfig.ConfigDialog(False)
            dlg.show_all()
            dlg.focus_field('tortoisehg.editor')
            dlg.run()
            dlg.hide()
            self.ui = ui.ui()
            self._parse_config()
            return

        lfile = util.localpath(files[0])
        thread = threading.Thread(target=doedit, name='edit:'+lfile)
        thread.setDaemon(True)
        thread.start()

