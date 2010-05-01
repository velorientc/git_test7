# gdialog.py - base window & dialogs for gtools
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
import pango

from mercurial import cmdutil, util, ui, hg, commands, error

from tortoisehg.util.i18n import _
from tortoisehg.util import settings, hglib, paths, shlib

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
        try:
            buttons = self.get_children()[0].get_children()[1].get_children()
            buttons[0].add_accelerator('clicked', accel_group, key,
                                       modifier, gtk.ACCEL_VISIBLE)
        except IndexError:
            pass

class CustomPrompt(gtk.MessageDialog):
    ''' Custom prompt dialog.  Provide a list of choices with ampersands
    to delineate response given for each choice (and keyboard
    accelerator). Default must be the index of one of the choice responses.
    '''
    # ret = CustomPrompt('Title', 'Message', self, ('&Yes', 'N&o'), 1).run()
    # ret will be (gtk.RESPONSE_DELETE_EVENT, 0 (for yes), or 1 (for no)
    def __init__(self, title, message, parent, choices, default=None,
                 esc=None, files=None):
        gtk.MessageDialog.__init__(self, parent, gtk.DIALOG_MODAL,
                gtk.MESSAGE_QUESTION)
        self.set_title(hglib.toutf(title))
        if files:
            msg = ''
            for i, file in enumerate(files):
                msg += '   %s\n' % file
                if i == 9:
                    msg += '   ...\n'
                    break
            message += '\n\n' + msg
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
        buttons[1].add_accelerator('clicked', accel_group, ord('y'),
                              0, gtk.ACCEL_VISIBLE)
        buttons[0].add_accelerator('clicked', accel_group, ord('n'),
                              0, gtk.ACCEL_VISIBLE)

class GWindow(gtk.Window):
    """
    gtk.Window based window for displaying mercurial information

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
            self.tooltips = gtklib.Tooltips()


    def test_opt(self, opt):
        return self.opts.get(opt, False)

    def _parse_config(self):
        self.rawfonts = hglib.getfontconfig(self.ui)
        self.fonts = {}
        for name, val in self.rawfonts.items():
            self.fonts[name[4:]] = pango.FontDescription(val)
        try:
            self.diffbottom = self.ui.configbool('gtools', 'diffbottom', False)
        except error.ConfigError:
            self.diffbottom = False


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
            self.tooltips.set_tip(tbutton, tip)
        if icon:
            image = gtklib.get_icon_image(icon)
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

    def helpindex(self, item):
        self.helpcontents(item, 'index.html')

    def helpcontents(self, item, url=None):
        'User selected Help->Contents from menu bar'
        if not url:
            url = self.get_help_url()
            if not url:
                return
        if not url.startswith('http'):
            fullurl = 'http://tortoisehg.org/manual/1.0/' + url
            # Use local CHM file if it can be found
            if os.name == 'nt' and paths.bin_path:
                chm = os.path.join(paths.bin_path, 'doc', 'TortoiseHg.chm')
                if os.path.exists(chm):
                    fullurl = (r'mk:@MSITStore:%s::/' % chm) + url
        shlib.browse_url(fullurl)

    def launch(self, item, app):
        import sys
        # Spawn background process and exit
        if hasattr(sys, 'frozen'):
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

        self.tooltips = gtklib.Tooltips()
        toolbar = gtk.Toolbar()
        tbuttons =  self.get_tbbuttons()
        for tbutton in tbuttons:
            toolbar.insert(tbutton, -1)
        for x in toolbar.get_children():
            x.set_homogeneous(True)
        self.toolbar = toolbar

        # Subclass returns the main body
        body = self.get_body()

        # Subclass provides extra stuff in bottom hbox
        extras = self.get_extras()

        menus = self.get_menu_list()
        if menus:
            allmenus = [
            dict(text=_('_Tools'), subitems=[
                dict(text=_('Repository Explorer'), func=self.launch,
                    args=['log'], icon='menulog.ico'),
                dict(text=_('Commit'), func=self.launch,
                    args=['commit'], icon='menucommit.ico'),
                dict(text=_('Datamine'), func=self.launch,
                    args=['datamine'], icon='menurepobrowse.ico'),
                dict(text=_('Recovery'), func=self.launch,
                    args=['recover'], icon='general.ico'),
                dict(text=_('Serve'), func=self.launch,
                    args=['serve'], icon='proxy.ico'),
                dict(text=_('Shelve'), func=self.launch,
                    args=['shelve'], icon='shelve.ico'),
                dict(text=_('Synchronize'), func=self.launch,
                    args=['synch'], icon='menusynch.ico'),
                dict(text=_('Settings'), func=self.launch,
                    args=['repoconfig'], icon='settings_repo.ico')])
                ] + menus + [
            dict(text=_('_Help'), subitems=[
                dict(text=_('Contents'), func=self.helpcontents,
                    icon=gtk.STOCK_INFO),
                dict(text=_('Index'), func=self.helpindex,
                    icon=gtk.STOCK_HELP),
                dict(text=_('About'), func=self.launch,
                    args=['about'], icon=gtk.STOCK_ABOUT)])
                ]
            def build(menus, nobuild=False):
                mb = gtklib.MenuBuilder()
                for d in menus:
                    text = d['text']
                    if text == '----':
                        mb.append_sep()
                        continue
                    subitems = d.get('subitems')
                    if subitems:
                        sub = build(subitems)
                        item = mb.append_submenu(text, sub, **d)
                    else:
                        if 'rg' in d:
                            d.update(group=self.menuitems.get(d['rg']))
                        item = mb.append(text, d.get('func'), **d)
                    name = d.get('name')
                    if name:
                        self.menuitems[name] = item
                if nobuild:
                    return mb.get_menus()
                return mb.build()
            menubar = gtk.MenuBar()
            for menu in build(allmenus, nobuild=True):
                menubar.append(menu)

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
            except error.LookupError, inst:
                Prompt(title + _(' Aborted'), str(inst) + 
                        _(', please refresh'), self).run()
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
            if dirname == '':
                dirname = 'root'
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

            paths = ['"%s"' % os.path.join(pathroot, f) for f in files]
            command = '%s %s' % (editor, ' '.join(paths))
            util.system(command,
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

MODE_NORMAL  = 'normal'
MODE_WORKING = 'working'

RESPONSE_FORCE_CLOSE = 1024

class GDialog(gtk.Dialog):
    """ gtk.Dialog based window for executing mercurial operations """
    def __init__(self, resizable=False, norepo=False):
        gtk.Dialog.__init__(self)
        gtklib.set_tortoise_icon(self, self.get_icon())
        gtklib.set_tortoise_keys(self)
        self.set_resizable(resizable)
        self.set_has_separator(False)
        self.earlyout = False

        self.ui = ui.ui()
        if norepo:
            repo = None
        else:
            try:
                repo = hg.repository(self.ui, path=paths.find_root())
            except error.RepoError:
                gtklib.idle_add_single_call(self.destroy)
                return
        self.repo = repo
        self.after_done = True

        # persistent settings
        name = self.get_setting_name()
        if name:
            self.settings = settings.Settings(name)

        # signal handler
        self.connect('realize', self.realized)

        # disable entire dialog
        self.set_sensitive(False)

    ### Overridable Functions ###

    def get_title(self, reponame):
        return 'TortoiseHg - %s' % reponame

    def get_icon(self):
        return 'thg_logo.ico'

    def get_defsize(self):
        return (-1, -1)

    def get_setting_name(self):
        return None

    def get_body(self, vbox):
        pass

    def get_extras(self, vbox):
        pass

    def get_buttons(self):
        return []

    def get_default_button(self):
        return None

    def get_action_map(self):
        return {}

    def switch_to(self, normal, working, cmd):
        pass

    def command_done(self, returncode, useraborted, *args):
        pass

    def before_show(self):
        pass

    def before_close(self):
        return True

    def load_settings(self):
        pass

    def store_settings(self):
        pass

    ### Public Functions ###

    def set_notify_func(self, func, *args):
        self.notify_func = func
        self.notify_args = args

    def set_after_done(self, close):
        self.after_done = close

    ### Internal Functions ###

    def after_init(self):
        from tortoisehg.hgtk import hgcmd
        self.get_extras(self.vbox)

        # CmdWidget
        self.cmd = hgcmd.CmdWidget()
        self.cmd.show_all()
        self.cmd.hide()
        self.vbox.pack_start(self.cmd, False, False, 6)

        # add Abort button
        self.action_area.add(self.buttons['abort'])

        # enable entire dialog
        self.set_sensitive(True)

        # focus on default button if needs
        name = self.get_default_button()
        if name:
            btn = self.buttons.get(name)
            if btn:
                btn.grab_focus()

    def do_switch_to(self, mode, cmd=True):
        if mode == MODE_NORMAL:
            normal = True
        elif mode == MODE_WORKING:
            normal = False
            self.buttons['abort'].grab_focus()
        else:
            raise _('unknown mode name: %s') % mode
        working = not normal

        if cmd:
            self.cmd.set_property('visible', working)
        self.buttons['abort'].set_property('visible', working)

        self.switch_to(normal, working, cmd)

    def abort(self):
        self.cmd.stop()
        self.cmd.show_log()
        self.do_switch_to(MODE_NORMAL, cmd=False)

    def execute_command(self, cmdline, *args):
        def cmd_done(returncode, useraborted):
            self.do_switch_to(MODE_NORMAL, cmd=False)
            self.command_done(returncode, useraborted, *args)
            if hasattr(self, 'notify_func') and self.notify_func:
                self.notify_func(*self.notify_args)
            if self.after_done and returncode == 0:
                if not self.cmd.is_show_log():
                    self.response(gtk.RESPONSE_CLOSE)
        self.do_switch_to(MODE_WORKING)
        self.cmd.execute(cmdline, cmd_done)

    ### Signal Handlers ###

    def realized(self, *args):
        # set title
        reponame = self.repo and hglib.get_reponame(self.repo) or ''
        self.set_title(self.get_title(reponame))

        # add user-defined buttons
        self.buttons = {}
        for name, label, res in self.get_buttons():
            btn = self.add_button(label, res)
            self.buttons[name] = btn

        # create Abort button (add later)
        btn = gtk.Button(_('Abort'))
        btn.connect('clicked', lambda *a: self.response(gtk.RESPONSE_CANCEL))
        self.buttons['abort'] = btn

        # construct dialog body
        self.get_body(self.vbox)
        if self.earlyout:
            gtklib.idle_add_single_call(self.destroy)
            return

        # load persistent settings
        self.load_settings()

        # dialog size
        defsize = self.get_defsize()
        if defsize != (-1, -1):
            self.set_default_size(*defsize)

        # signal handler
        self.connect('response', self.dialog_response)

        # prepare to show
        self.before_show()
        self.vbox.show_all()
        gtklib.idle_add_single_call(self.after_init)

    def dialog_response(self, dialog, response_id):
        # User-defined buttons
        actmap = self.get_action_map()
        if actmap.has_key(response_id):
            actmap[response_id]()
        # Forced close
        elif response_id == RESPONSE_FORCE_CLOSE:
            if self.cmd.is_alive():
                self.abort()
            self.store_settings()
            self.destroy()
            return # close dialog
        # Cancel button or dialog closing by the user
        elif response_id in (gtk.RESPONSE_CLOSE, gtk.RESPONSE_DELETE_EVENT):
            if self.cmd.is_alive():
                ret = Confirm(_('Confirm Abort'), [], self,
                              _('Do you want to abort?')).run()
                if ret == gtk.RESPONSE_YES:
                    self.abort()
            else:
                close = self.before_close()
                if close:
                    self.store_settings()
                    self.destroy()
                    return # close dialog
        # Abort button
        elif response_id == gtk.RESPONSE_CANCEL:
            self.abort()
        else:
            raise _('unexpected response id: %s') % response_id

        self.run() # don't close dialog
