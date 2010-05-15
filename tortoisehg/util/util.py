# -*- coding: utf-8 -*-
# util functions
#
# Copyright (C) 2009-2010 Logilab. All rights reserved.
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.
"""
Several helper functions
"""
import os
import string
from mercurial import cmdutil

def tounicode(string):
    """
    Tries to convert s into a unicode string
    """
    for encoding in ('utf-8', 'iso-8859-15', 'cp1252'):
        try:
            return unicode(string, encoding)
        except UnicodeDecodeError:
            pass
    return unicode(string, 'utf-8', 'replace')
        
def has_closed_branch_support(repo):
    """
    Return True is repository have support for closed branches
    """
    # what a hack... 
    return "closed" in repo.heads.im_func.func_code.co_varnames

def isexec(filectx):
    """
    Return True is the file at filectx revision is executable
    """
    if hasattr(filectx, "isexec"):        
        return filectx.isexec()
    return "x" in filectx.flags()
    
def exec_flag_changed(filectx):
    """
    Return True if the file referenced by filectx has changed its exec
    flag
    """
    flag = isexec(filectx)
    parents = filectx.parents()
    if not parents:
        return ""
    
    pflag = isexec(parents[0])
    if flag != pflag:
        if flag:
            return "set"
        else:
            return "unset"
    return ""

def isbfile(filename):
    return filename and filename.startswith('.hgbfiles' + os.sep)

def bfilepath(filename):
    return filename and filename.replace('.hgbfiles' + os.sep, '')

def find_repository(path):
    """returns <path>'s mercurial repository

    None if <path> is not under hg control
    """
    path = os.path.abspath(path)
    while not os.path.isdir(os.path.join(path, ".hg")):
        oldpath = path
        path = os.path.dirname(path)
        if path == oldpath:
            return None
    return path

def rootpath(repo, rev, path):
    """return the path name of 'path' relative to repo's root at
    revision rev;
    path is relative to cwd
    """  
    ctx = repo[rev]        
    filenames = list(ctx.walk(cmdutil.match(repo, [path], {})))
    if len(filenames) != 1 or filenames[0] not in ctx.manifest():
        return None
    else:
        return filenames[0]
    
class Curry(object):
    """Curryfication de fonction (http://fr.wikipedia.org/wiki/Curryfication)"""
    def __init__(self, function, *additional_args, **additional_kwargs):
        self.func = function
        self.additional_args = additional_args
        self.additional_kwargs = additional_kwargs

    def __call__(self, *args, **kwargs):
        args += self.additional_args
        kwarguments = self.additional_kwargs.copy()
        kwarguments.update(kwargs)
        return self.func(*args, **kwarguments)

CONTROL_CHARS = [chr(ci) for ci in range(32)]
TR_CONTROL_CHARS = [' '] * len(CONTROL_CHARS)
for c in ('\n', '\r', '\t'):
    TR_CONTROL_CHARS[ord(c)] = c
TR_CONTROL_CHARS[ord('\f')] = '\n'
TR_CONTROL_CHARS[ord('\v')] = '\n'
ESC_CAR_TABLE = string.maketrans(''.join(CONTROL_CHARS),
                                 ''.join(TR_CONTROL_CHARS))
ESC_UCAR_TABLE = unicode(ESC_CAR_TABLE, 'latin1')

def xml_escape(data):
    """escapes XML forbidden characters in attributes and PCDATA"""
    if isinstance(data, unicode):
        data = data.translate(ESC_UCAR_TABLE)
    else:
        data = data.translate(ESC_CAR_TABLE)
    return (data.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
            .replace('"','&quot;').replace("'",'&#39;'))

def format_desc(desc, width):
    """
    Helper function to format a ctx description for oneliner
    representation (summary view)
    """
    desc = xml_escape(tounicode(desc).split('\n', 1)[0])
    if len(desc) > width:
        desc = desc[:width] + '...'
    return desc

