# reggen.py - registry file generator for Windows shell context menus
#
# Copyright 2009 Yuki KODAMA <endflow.net@gmail.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

import sys
import os.path
import glob
import re
import codecs

# copy of 'nautilus-thg.py'
def _thg_path():
    pfile = __file__
    if pfile.endswith('.pyc'):
        pfile = pfile[:-1]
    path = os.path.dirname(os.path.dirname(os.path.realpath(pfile)))
    thgpath = os.path.normpath(path)
    testpath = os.path.join(thgpath, 'thgutil')
    if os.path.isdir(testpath) and thgpath not in sys.path:
        sys.path.insert(0, thgpath)
_thg_path()

from thgutil.menuthg import thgcmenu

regkeytmpl = u'[HKEY_CURRENT_USER\\Software\\TortoiseHg\\CMenu\\%s\\%s]'
regheaders = (  u'Windows Registry Editor Version 5.00',
                u'',
                u'[HKEY_CURRENT_USER\\Software\\TortoiseHg]',
                u'"CMenuLang"="%(lang)s"',
                u'',
                u'[HKEY_CURRENT_USER\\Software\\TortoiseHg\\CMenu]',
                u'',
                u'[HKEY_CURRENT_USER\\Software\\TortoiseHg\\CMenu\\%(lang)s]')

# regex patterns used to extract strings from PO files
pat_id = re.compile(u'^msgid "([^\\"]+)"')
pat_str = re.compile(u'^msgstr "([^\\"]+)"')
def lookup(file):
    def stripmsg(line, pat):
        m = pat.match(line)
        if m:
            return m.group(1)
    # acquire all translatable strings
    # and set fallback messages
    i18n = {}
    msgids = []
    for cmenu in thgcmenu.values():
        label = cmenu['label']['id'].decode('utf-8')
        msgids.append(label)
        i18n[label] = label
        help = cmenu['help']['id'].decode('utf-8')
        msgids.append(help)
        i18n[help] = help
    # lookup PO file
    if file:
        foundmsgid = False
        f = codecs.open(file, 'r', 'utf-8')
        for line in f.readlines():
            line = line.rstrip(u'\r\n')
            if foundmsgid:
                msgstr = stripmsg(line, pat_str)
                if msgstr:
                    i18n[msgid] = msgstr
                foundmsgid = False
            else:
                msgid = stripmsg(line, pat_id)
                if msgid and msgid in msgids:
                    foundmsgid = True
        f.close()
    return i18n

def wopen(path):
    newfile = codecs.open(path, 'w','utf-16-le')
    newfile.write(codecs.BOM_UTF16_LE.decode('utf-16-le'))
    def write(lines, newlines=2):
        if isinstance(lines, (str, unicode)):
            buf = lines
        else:
            buf = u'\r\n'.join(lines)
        buf = (buf + (u'\r\n' * newlines))
        newfile.write(buf)
    def close():
        newfile.close()
    return write, close

# enumerate available languages
langinfo = [{'code': u'en_US', 'file': None}]
lang_pat = re.compile(u'^tortoisehg-([^\\.]+)\\.po$')
for file in glob.glob(u'../i18n/*.po'):
    m = lang_pat.match(os.path.basename(file))
    langinfo.append({'code': m.group(1), 'file': os.path.abspath(file)})

# output REG files
for lang in langinfo:
    write, close = wopen(u'thg-cmenu-%s.reg' % lang['code'])
    write([h % {'lang': lang['code']} for h in regheaders])
    i18n = lookup(lang['file'])
    for hgcmd, cmenu in thgcmenu.items():
        write(regkeytmpl % (lang['code'], hgcmd.decode('utf-8')), 1)
        write((u'"menuText"="%s"' % i18n[cmenu['label']['id'].decode('utf-8')],
               u'"helpText"="%s"' % i18n[cmenu['help']['id'].decode('utf-8')]))
    close()
