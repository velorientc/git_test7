#include "stdafx.h"
#include "ShellExt.h"
#include "TortoiseUtils.h"

#define CALL_MEMBER_FN(object,ptrToMember)  ((object).*(ptrToMember)) 
typedef STDMETHODIMP (CShellExt::*MenuAction)
        (HWND hParent, LPCSTR pszWorkingDir, LPCSTR pszCmd, LPCSTR pszParam,
                int iShowCmd); 

typedef struct {
    std::string name;
    std::string menuText;
    std::string helpText;
    std::string iconName;
    MenuAction action;
    int idCmd;
    ULONG flags;
} MenuDescription;

typedef std::map<std::string, MenuDescription> MenuDescriptionMap;
typedef std::map<int, MenuDescription> MenuIdCmdMap;


MenuDescription menuDescList[] = { 
    {"commit", "HG Commit...", "Commit changes in repository",
        "menucommit.ico", &CShellExt::CM_Commit, 0, 0},
    {"status", "View File Status", "Repository status & changes",
        "menushowchanged.ico", &CShellExt::CM_Status, 0, 0},
    {"log", "View Changelog", "View change history in repository",
        "menulog.ico", &CShellExt::CM_Log, 0, 0},
    {"synch", "Synchronize", "Synchronize with remote repository",
        "menusynch.ico", &CShellExt::CM_Synch, 0, 0},
    {"serve", "Web Server", "Start web server for this repository",
        "proxy.ico", &CShellExt::CM_Serve, 0, 0},
    {"update", "Update To Revision", "Update working directory",
        "menucheckout.ico", &CShellExt::CM_Update, 0, 0},
    {"recover", "Recovery...", "General repair and recovery of repositor",
        "general.ico", &CShellExt::CM_Recover, 0, 0},
    {"thgstatus", "Update Icons", "Update icons for this repository",
        "", &CShellExt::CM_thgstatus, 0, 0},
    {"userconf", "Global Settings", "Configure user wide settings",
        "settings_user.ico", &CShellExt::CM_Userconf, 0, 0},
    {"repoconf", "Repository Settings", "Configure settings local to this repository",
        "settings_repo.ico", &CShellExt::CM_Repoconf, 0, 0},
    {"about", "About...", "Show About Dialog",
        "menuabout.ico", &CShellExt::CM_About, 0, 0},

    // template
    {"", "", "",
        ".ico", NULL, 0, 0},
};

MenuDescriptionMap MenuDescMap;
MenuIdCmdMap MenuIdMap;

extern HMENU		hSubMenu;
extern HINSTANCE    g_hmodThisDll;	

void AddMenuList(int idCmd, std::string name)
{    
    TDEBUG_TRACE("AddMenuList: idCmd = " << idCmd << " name = " << name);
    MenuIdMap[idCmd] = MenuDescMap[name];
}

void InitMenuMaps()
{
    if (MenuDescMap.empty())
    {
        int sz = sizeof(menuDescList) / sizeof(MenuDescription);
        for (int i=0; i < sz; i++)
        {
            MenuDescription md = menuDescList[i];
            TDEBUG_TRACE("InitMenuMaps: adding " << md.name);
            MenuDescMap[md.name] = md;
        }
    }
           
    MenuIdMap.clear();
}

void InsertMenuItemWithIcon(HMENU hMenu, int indexMenu, int idCmd,
        std::string menuText, std::string iconName)
{
	MENUITEMINFO mi;
	mi.cbSize = sizeof(mi);
    mi.dwTypeData = const_cast<char*> (menuText.c_str());
    mi.cch = static_cast<UINT> (menuText.length());
    mi.wID = idCmd;
    mi.fType = MFT_STRING;

    HICON h = GetTortoiseIcon(iconName);
    if (h)
    {
        mi.fMask = MIIM_STRING | MIIM_FTYPE | MIIM_ID | MIIM_BITMAP | MIIM_DATA;
        mi.dwItemData = (ULONG_PTR) h;
        mi.hbmpItem = HBMMENU_CALLBACK;
    }
    else
    {
        TDEBUG_TRACE("    InsertMenuItemWithIcon: can't find " + iconName);            
        mi.fMask = MIIM_TYPE | MIIM_ID;
    }
    InsertMenuItem(hMenu, indexMenu, TRUE, &mi);
}

void InsertSubMenuItemWithIcon(HMENU hMenu, HMENU hSubMenu, int indexMenu, int idCmd,
        std::string menuText, std::string iconName)
{
    MENUITEMINFO mi;
    mi.cbSize = sizeof(mi);
    mi.fMask = MIIM_SUBMENU | MIIM_STRING | MIIM_ID;
    mi.fType = MFT_STRING;
    mi.dwTypeData = const_cast<char*> (menuText.c_str());
    mi.cch = static_cast<UINT> (menuText.length());
    mi.wID = idCmd;
    mi.hSubMenu = hSubMenu;
    HICON h = GetTortoiseIcon(iconName);
    if (h)
    {
        mi.fMask = MIIM_FTYPE | MIIM_STRING | MIIM_SUBMENU | MIIM_ID |
                   MIIM_BITMAP | MIIM_DATA;
        mi.dwItemData = (ULONG_PTR) h;
        mi.hbmpItem = HBMMENU_CALLBACK;
    }
    else
    {
        TDEBUG_TRACE("    InsertSubMenuItemWithIcon: can't find " + iconName);            
    }
    InsertMenuItem(hMenu, indexMenu, TRUE, &mi);
}

void InsertMenuItemByName(HMENU hMenu, std::string name, int indexMenu,
        int idCmd, int idCmdFirst)
{
    TDEBUG_TRACE("InsertMenuItemByName: name = " << name);
    MenuDescriptionMap::iterator iter = MenuDescMap.find(name);
    if (iter == MenuDescMap.end())
    {
        TDEBUG_TRACE("InsertMenuItemByName: can't find menu info for " << name);
        return;
    }

    MenuDescription md = MenuDescMap[name];
    AddMenuList(idCmd - idCmdFirst, name);
    InsertMenuItemWithIcon(hMenu, indexMenu, idCmd, md.menuText, md.iconName);
}

//	IContextMenu
STDMETHODIMP
CShellExt::QueryContextMenu(HMENU hMenu, UINT indexMenu, UINT idCmdFirst,
		UINT idCmdLast, UINT uFlags)
{
    TDEBUG_TRACE("CShellExt::QueryContextMenu");
    InitMenuMaps();
    
    UINT idCmd = idCmdFirst;
	BOOL bAppendItems = TRUE;

	if((uFlags & 0x000F) == CMF_NORMAL)
		bAppendItems = TRUE;
	else if (uFlags & CMF_VERBSONLY)
		bAppendItems = TRUE;
	else if (uFlags & CMF_EXPLORE)
		bAppendItems = TRUE;
	else
		bAppendItems = FALSE;

    if (!bAppendItems)
        return NOERROR;

    // check if target directory is a Mercurial repository
    bool isHgrepo = false;
    std::string cwd;
    if (!myFolder.empty())
    {
        cwd = myFolder;
    }
    else if (!myFiles.empty())
    {
        cwd = IsDirectory(myFiles[0])? myFiles[0] : DirName(myFiles[0]);
    }
    if (!cwd.empty())
        isHgrepo = IsHgRepo(cwd);
    
    // start building TortoiseHg menus and submenus
    InsertMenu(hMenu, indexMenu, MF_SEPARATOR | MF_BYPOSITION, 0, NULL);
    indexMenu++;

    if (isHgrepo)
        InsertMenuItemByName(hMenu, "commit", indexMenu++, idCmd++, idCmdFirst);

    TDEBUG_TRACE("  CShellExt::QueryContextMenu: adding sub menus");
    HMENU hSubMenu = CreatePopupMenu();
    int indexSubMenu = 0;
    if(hSubMenu)
    {
        if (isHgrepo)
        {
            InsertMenuItemByName(hSubMenu, "status", indexSubMenu++, idCmd++, idCmdFirst);

            InsertMenu(hSubMenu, indexSubMenu++, MF_SEPARATOR | MF_BYPOSITION,
                    0, NULL);
            InsertMenuItemByName(hSubMenu, "log", indexSubMenu++, idCmd++, idCmdFirst);

            InsertMenu(hSubMenu, indexSubMenu++, MF_SEPARATOR | MF_BYPOSITION,
                    0, NULL);
            InsertMenuItemByName(hSubMenu, "update", indexSubMenu++, idCmd++, idCmdFirst);
            
            InsertMenu(hSubMenu, indexSubMenu++, MF_SEPARATOR | MF_BYPOSITION,
                    0, NULL);
            InsertMenuItemByName(hSubMenu, "synch", indexSubMenu++, idCmd++, idCmdFirst);
            InsertMenuItemByName(hSubMenu, "recover", indexSubMenu++, idCmd++, idCmdFirst);
            InsertMenuItemByName(hSubMenu, "serve", indexSubMenu++, idCmd++, idCmdFirst);
            InsertMenuItemByName(hSubMenu, "thgstatus", indexSubMenu++, idCmd++, idCmdFirst);

            InsertMenu(hSubMenu, indexSubMenu++, MF_SEPARATOR | MF_BYPOSITION,
                    0, NULL);
            InsertMenuItemByName(hSubMenu, "userconf", indexSubMenu++, idCmd++, idCmdFirst);
        }
        
        InsertMenuItemByName(hSubMenu, "repoconf", indexSubMenu++, idCmd++, idCmdFirst);

        InsertMenu(hSubMenu, indexSubMenu++, MF_SEPARATOR | MF_BYPOSITION,
                0, NULL);

        InsertMenuItemByName(hSubMenu, "about", indexSubMenu++, idCmd++, idCmdFirst);
    }

    TDEBUG_TRACE("  CShellExt::QueryContextMenu: adding main THG menu");
    InsertSubMenuItemWithIcon(hMenu, hSubMenu, indexMenu++, idCmd++,
            "TortoiseHG...", "hg.ico");

    InsertMenu(hMenu, indexMenu++, MF_SEPARATOR | MF_BYPOSITION, 0, NULL);

    return ResultFromShort(idCmd - idCmdFirst);
}

STDMETHODIMP
CShellExt::InvokeCommand(LPCMINVOKECOMMANDINFO lpcmi)
{
    TDEBUG_TRACE("CShellExt::InvokeCommand");

    HRESULT hr = E_INVALIDARG;
    if (!HIWORD(lpcmi->lpVerb))
    {
        UINT idCmd = LOWORD(lpcmi->lpVerb);
        TDEBUG_TRACE("CShellExt::InvokeCommand: idCmd = " << idCmd);
        MenuIdCmdMap::iterator iter = MenuIdMap.find(idCmd);
        if(iter != MenuIdMap.end())
        {
            MenuAction action = MenuIdMap[idCmd].action;
            hr = CALL_MEMBER_FN(*this, action)(lpcmi->hwnd, lpcmi->lpDirectory,
                    lpcmi->lpVerb, lpcmi->lpParameters, lpcmi->nShow);
        }
        else
        {
            TDEBUG_TRACE("CShellExt::InvokeCommand: action not found for idCmd " << idCmd);
        }
    }
    return hr;
}

STDMETHODIMP
CShellExt::GetCommandString(UINT idCmd, UINT uFlags, UINT FAR *reserved,
		LPSTR pszName, UINT cchMax)
{
    TDEBUG_TRACE("CShellExt::GetCommandString");

	*pszName = 0;
	char *psz;

    TDEBUG_TRACE("CShellExt::GetCommandString: idCmd = " << idCmd);
    MenuIdCmdMap::iterator iter = MenuIdMap.find(idCmd);
    if (iter != MenuIdMap.end())
    {
        TDEBUG_TRACE("CShellExt::GetCommandString: name = " << MenuIdMap[idCmd].name);
        psz = (char*)MenuIdMap[idCmd].helpText.c_str();
    }
    else
    {
        TDEBUG_TRACE("CShellExt::GetCommandString: can't find idCmd " << idCmd);
        psz = "";
    }

	wcscpy((wchar_t*)pszName, _WCSTR(psz));
    return NOERROR;
}

STDMETHODIMP CShellExt::HandleMenuMsg(UINT uMsg, WPARAM wParam, LPARAM lParam)
{
    LRESULT res;
    return HandleMenuMsg2(uMsg, wParam, lParam, &res);
}

STDMETHODIMP CShellExt::HandleMenuMsg2(UINT uMsg, WPARAM wParam, LPARAM lParam, LRESULT* pResult)
{
    TDEBUG_ENTER("CShellExt::HandleMenuMsg2");
    // A great tutorial on owner drawn menus in shell extension can be found
    // here: http://www.codeproject.com/shell/shellextguide7.asp

    LRESULT res;
    if (!pResult)
        pResult = &res;
    *pResult = FALSE;

    switch (uMsg)
    {
    case WM_MEASUREITEM:
    {
        MEASUREITEMSTRUCT* lpmis = (MEASUREITEMSTRUCT*)lParam;
        if (lpmis==NULL)
            break;
        lpmis->itemWidth += 2;
        if(lpmis->itemHeight < 16)
            lpmis->itemHeight = 16;
        *pResult = TRUE;
    }
    break;
    case WM_DRAWITEM:
    {
        DRAWITEMSTRUCT* lpdis = (DRAWITEMSTRUCT*)lParam;
        if (!lpdis || (lpdis->CtlType != ODT_MENU) || !lpdis->itemData)
            break; //not for a menu
        DrawIconEx(lpdis->hDC,
                   lpdis->rcItem.left - 16,
                   lpdis->rcItem.top + (lpdis->rcItem.bottom - lpdis->rcItem.top - 16) / 2,
                   (HICON) lpdis->itemData, 16, 16,
                   0, 0, DI_NORMAL);
        *pResult = TRUE;
    }
    break;
    default:
        return NOERROR;
    }

    return NOERROR;
}
