#include "stdafx.h"
#include "TortoiseUtils.h"

#include "CShellExtDnd.h"


// According to http://msdn.microsoft.com/en-us/library/bb776094%28VS.85%29.aspx
// the help texts for the commands should be reasonably short (under 40 characters)

static const MenuDescription CDndMenuDescList[] =
{
    {"drag_move",   L"Hg Move versioned item(s) here",
                    L"", "hg.ico", 0},
    {"drag_copy",   L"Hg Copy versioned item(s) here",
                    L"", "hg.ico", 0},
    /* Add new items here */

    // template
    //{"", L"", L"", ".ico", 0},
};


static const char* const DropMenu =
    "drag_move drag_copy"
;


#define ResultFromShort(i)  ResultFromScode(MAKE_SCODE(SEVERITY_SUCCESS, 0, (USHORT)(i)))

// IContextMenu
STDMETHODIMP
CShellExtDnd::QueryContextMenu(
    HMENU hMenu, UINT indexMenu, UINT idCmdFirst, UINT idCmdLast, UINT uFlags)
{
    TDEBUG_TRACE("CShellExtDnd::QueryContextMenu");

    if ((uFlags & CMF_DEFAULTONLY)!=0)
        return S_OK;                    //we don't change the default action

    if (((uFlags & 0x000f)!=CMF_NORMAL)&&(!(uFlags & CMF_EXPLORE))&&(!(uFlags & CMF_VERBSONLY)))
        return S_OK;


    UINT idCmd = idCmdFirst;

    InitMenuMaps(CDndMenuDescList, sizeof(CDndMenuDescList) / sizeof(MenuDescription));

    typedef std::vector<std::string> entriesT;
    typedef entriesT::const_iterator entriesIter;

    const char* entries_string = DropMenu;
    entriesT entries;
    Tokenize(entries_string, entries, " ");

    for (entriesIter i = entries.begin(); i != entries.end(); i++)
    {
        std::string name = *i;
        InsertMenuItemByName(
            hMenu, name, indexMenu++,
            idCmd++, idCmdFirst, L""
        );
    }

    // separator
    if (idCmd != idCmdFirst)
        InsertMenu(hMenu, indexMenu++, MF_SEPARATOR|MF_BYPOSITION, 0, NULL);

    TweakMenuForVista(hMenu);

    return ResultFromShort(idCmd - idCmdFirst);
}


void CShellExtDnd::RunDialog(const std::string &cmd)
{
    if (cmd == "drag_move" || cmd == "drag_copy") {
		//Append the current directory as the dest
        myFiles.push_back(myFolder);
    }
    CShellExtCMenu::RunDialog(cmd);
}


STDMETHODIMP CShellExtDnd::Initialize(
    LPCITEMIDLIST pIDFolder, LPDATAOBJECT pDataObj, HKEY hRegKey)
{
    TCHAR name[MAX_PATH+1];

    PrintDebugHeader(pIDFolder, pDataObj);

    myFolder.clear();
    myFiles.clear();

    // if a directory background
    if (pIDFolder)
    {
        SHGetPathFromIDList(pIDFolder, name);
        TDEBUG_TRACE("  Folder " << name);
        myFolder = name;
    }

    std::string root;

    //short circuit if we're dragging into a non-Hg repository
    if (myFolder.empty() || (root = GetHgRepoRoot(myFolder)).empty())
    {
        TDEBUG_TRACE("  drag into a non-Hg repos directory");
        return E_FAIL;
    }

    if (pDataObj)
    {
        FORMATETC fmt = { CF_HDROP, NULL, DVASPECT_CONTENT, -1, TYMED_HGLOBAL };
        STGMEDIUM stg = { TYMED_HGLOBAL };
        if (SUCCEEDED(pDataObj->GetData(&fmt, &stg)) && stg.hGlobal)
        {
            HDROP hDrop = (HDROP) GlobalLock(stg.hGlobal);

            if (hDrop)
            {
                UINT uNumFiles = DragQueryFile(hDrop, 0xFFFFFFFF, NULL, 0);
                TDEBUG_TRACE("  hDrop uNumFiles = " << uNumFiles);
                for (UINT i = 0; i < uNumFiles; ++i) {
                    if (DragQueryFile(hDrop, i, name, MAX_PATH) > 0)
                    {
                        TDEBUG_TRACE("  DragQueryFile [" << i << "] = " << name);
                        if (GetHgRepoRoot(name) != root)
                        {
                            TDEBUG_TRACE("  " << name << " isn't in target dir repository");
                            myFiles.clear();
                            break;
					    }
                        myFiles.push_back(name);
                    }
                }
            }
            else
            {
                TDEBUG_TRACE("  hDrop is NULL ");
            }

            GlobalUnlock(stg.hGlobal);
            if (stg.pUnkForRelease)
            {
                IUnknown* relInterface = (IUnknown*) stg.pUnkForRelease;
                relInterface->Release();
            }
        }
        else
        {
            TDEBUG_TRACE("  pDataObj->GetData failed");
        }
    }

    // disable context menu if neither the folder nor the files
    // have been found
    if (myFiles.empty()) {
        TDEBUG_TRACE("  shell extension not available on this object");
        return E_FAIL;
    } else {
        return S_OK;
    }
}


CShellExtDnd::CShellExtDnd(const char dummy) :
    CShellExtCMenu(dummy)
{
}


CShellExtDnd::~CShellExtDnd()
{
}
