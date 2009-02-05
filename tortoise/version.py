# Published under the GNU GPL, v2 or later.
# Copyright (C) 2009 Steve Borho <steve@borho.org>

def get_version():
    try:
        import __version__
        return __version__.version
    except ImportError:
        return 'unknown'
