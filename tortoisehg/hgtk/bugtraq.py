from ctypes import *
import comtypes
import pythoncom
from comtypes import IUnknown, GUID, COMMETHOD, POINTER
from comtypes.typeinfo import ITypeInfo
from comtypes.client import CreateObject
from comtypes.automation import _midlSAFEARRAY
from _winreg import *

class IBugTraqProvider(IUnknown):
    _iid_ = GUID("{298B927C-7220-423C-B7B4-6E241F00CD93}")
    _methods_ = [
       COMMETHOD([], HRESULT, "ValidateParameters",
                       (['in'], comtypes.c_long, "hParentWnd"),
                       (['in'], comtypes.BSTR, "parameters"),
                       (['out', 'retval'], POINTER(comtypes.c_int16), "pRetVal") ),
       COMMETHOD([], HRESULT, "GetLinkText",
                       (['in'], comtypes.c_long, "hParentWnd"),
                       (['in'], comtypes.BSTR, "parameters"),
                       (['out', 'retval'], POINTER(comtypes.BSTR), "pRetVal") ),
       COMMETHOD([], HRESULT, "GetCommitMessage",
                       (['in'], comtypes.c_long, "hParentWnd"),
                       (['in'], comtypes.BSTR, "parameters"),
                       (['in'], comtypes.BSTR, "commonRoot"),
                       (['in'], _midlSAFEARRAY(comtypes.BSTR), "pathList"),
                       (['in'], comtypes.BSTR, "originalMessage"),
                       (['out', 'retval'], POINTER(comtypes.BSTR), "pRetVal") )
       ]

class IBugTraqProvider2(IBugTraqProvider):
    _iid_ = GUID("{C5C85E31-2F9B-4916-A7BA-8E27D481EE83}")
    _methods_ = [
    COMMETHOD([], HRESULT, "GetCommitMessage2",
                    (['in'], comtypes.c_long, "hParentWnd"),
                    (['in'], comtypes.BSTR, "parameters"),
                    (['in'], comtypes.BSTR, "commonURL"),
                    (['in'], comtypes.BSTR, "commonRoot"),
                    (['in'], _midlSAFEARRAY(comtypes.BSTR), "pathList"),
                    (['in'], comtypes.BSTR, "originalMessage"),
                    (['in'], comtypes.BSTR, "bugID"),
                    (['out'], POINTER(comtypes.BSTR), "bugIDOut"),
                    (['out'], POINTER(_midlSAFEARRAY(comtypes.BSTR)), "revPropNames"),
                    (['out'], POINTER(_midlSAFEARRAY(comtypes.BSTR)), "revPropValues"),
                    (['out', 'retval'], POINTER(comtypes.BSTR), "pRetVal") ),
    COMMETHOD([], HRESULT, "CheckCommit",
                    (['in'], comtypes.c_long, "hParentWnd"),
                    (['in'], comtypes.BSTR, "parameters"),
                    (['in'], comtypes.BSTR, "commonURL"),
                    (['in'], comtypes.BSTR, "commonRoot"),
                    (['in'], _midlSAFEARRAY(comtypes.BSTR), "pathList"),
                    (['in'], comtypes.BSTR, "commitMessage"),
                    (['out', 'retval'], POINTER(comtypes.BSTR), "pRetVal") ),
    COMMETHOD([], HRESULT, "OnCommitFinished",
                    (['in'], comtypes.c_long, "hParentWnd"),
                    (['in'], comtypes.BSTR, "commonRoot"),
                    (['in'], _midlSAFEARRAY(comtypes.BSTR), "pathList"),
                    (['in'], comtypes.BSTR, "logMessage"),
                    (['in'], comtypes.c_long, "revision"),
                    (['out', 'retval'], POINTER(comtypes.BSTR), "pRetVal") ),
    COMMETHOD([], HRESULT, "HasOptions",
                    (['out', 'retval'], POINTER(comtypes.c_int16), "pRetVal") ),
    COMMETHOD([], HRESULT, "ShowOptionsDialog",
                    (['in'], comtypes.c_long, "hParentWnd"),
                    (['in'], comtypes.BSTR, "parameters"),
                    (['out', 'retval'], POINTER(comtypes.BSTR), "pRetVal") )
    ]


class BugTraq:
    #svnjiraguid = "{CF732FD7-AA8A-4E9D-9E15-025E4D1A7E9D}"

    def __init__(self, guid):
        self.guid = guid
        self.bugtr = None

    def _get_bugtraq_object(self):
        if self.bugtr == None:
            obj = CreateObject(self.guid)
            self.bugtr = obj.QueryInterface(IBugTraqProvider2)
        return self.bugtr

    def get_commit_message(self, parameters, logmessage):
        commonurl = ""
        commonroot = ""
        bugid = ""
        bstrarray = _midlSAFEARRAY(comtypes.BSTR)
        pathlist = bstrarray.from_param(())

        bugtr = self._get_bugtraq_object()
        (bugid, revPropNames, revPropValues, newmessage) = bugtr.GetCommitMessage2(
                0, parameters, commonurl, commonurl, pathlist, logmessage, bugid)
        return newmessage

    def on_commit_finished(self, logmessage):
        commonroot = ""
        bstrarray = _midlSAFEARRAY(comtypes.BSTR)
        pathlist = bstrarray.from_param(())

        bugtr = self._get_bugtraq_object()
        errormessage = bugtr.OnCommitFinished(0, commonroot, pathlist,
                logmessage, 0)
        return errormessage
        
    def show_options_dialog(self, options):
        if not self.has_options():
            return ""

        bugtr = self._get_bugtraq_object()
        options = bugtr.ShowOptionsDialog(0, options)
        return options
    
    def has_options(self):
        bugtr = self._get_bugtraq_object()
        return bugtr.HasOptions() != 0
        
    def get_link_text(self, parameters):
        bugtr = self._get_bugtraq_object()
        return bugtr.GetLinkText(0, parameters)

def get_issue_plugins():
    cm = pythoncom.CoCreateInstance(pythoncom.CLSID_StdComponentCategoriesMgr,
            None, pythoncom.CLSCTX_INPROC,pythoncom.IID_ICatInformation)
    CATID_BugTraqProvider = pythoncom.MakeIID(
            "{3494FA92-B139-4730-9591-01135D5E7831}")
    ret = []
    enumerator = cm.EnumClassesOfCategories((CATID_BugTraqProvider,),())
    while 1:
        clsid = enumerator.Next();
        if clsid == ():
            break;

        ret.extend(clsid)
    return ret

def get_plugin_name(clsid):
    key = OpenKey(HKEY_CLASSES_ROOT, r"CLSID\%s" % clsid)
    keyvalue = QueryValueEx(key, None) 
    key.Close()
    return keyvalue[0]

def get_issue_plugins_with_names():
    pluginclsids = get_issue_plugins()
    return [(key, get_plugin_name(key)) for key in pluginclsids]


