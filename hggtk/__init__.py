import pygtk
pygtk.require('2.0')
import gtk

# Default icon for apps which do not set one
from shlib import get_tortoise_icon
gtk.window_set_default_icon_from_file(get_tortoise_icon("hg.ico"))
