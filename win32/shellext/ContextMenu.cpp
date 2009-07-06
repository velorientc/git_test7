#include "stdafx.h"
#include "ShellExt.h"
#include "TortoiseUtils.h"
#include "StringUtils.h"
#include "Dirstatecache.h"
#include "Thgstatus.h"
#include "Winstat.h"
#include "InitStatus.h"
#include <map>


struct MenuDescription
{
    std::string name;
    std::string menuText;
    std::string helpText;
    std::string iconName;
    UINT idCmd;
};

// According to http://msdn.microsoft.com/en-us/library/bb776094%28VS.85%29.aspx
// the help texts for the commands should be reasonably short (under 40 characters)

MenuDescription menuDescList[] =
{
    {"commit",      "Commit...",
                    "Commit changes in repository",
                    "menucommit.ico", 0},
    {"init",        "Create Repository Here",
                    "Create a new repository",
                    "menucreaterepos.ico", 0},
    {"clone",       "Clone a Repository",
                    "Create clone here from source",
                    "menuclone.ico", 0},
    {"status",      "View File Status",
                    "Repository status & changes",
                    "menushowchanged.ico", 0},
    {"shelve",      "Shelve Changes",
                    "Shelve or unshelve file changes",
                    "shelve.ico", 0},
    {"add",         "Add Files",
                    "Add files to version control",
                    "menuadd.ico", 0},
    {"revert",      "Revert Files",
                    "Revert file changes",
                    "menurevert.ico", 0},
    {"remove",      "Remove Files",
                    "Remove files from version control",
                    "menudelete.ico", 0},
    {"rename",      "Rename File",
                    "Rename file or directory",
                    "general.ico", 0},
    {"log",         "View Changelog",
                    "View change history in repository",
                    "menulog.ico", 0},
    {"synch",       "Synchronize",
                    "Synchronize with remote repository",
                    "menusynch.ico", 0},
    {"serve",       "Web Server",
                    "Start web server for this repository",
                    "proxy.ico", 0},
    {"update",      "Update To Revision",
                    "Update working directory",
                    "menucheckout.ico", 0},
    {"recover",     "Recovery...",
                    "Repair and recovery of repository",
                    "general.ico", 0},
    {"thgstatus",   "Update Icons",
                    "Update icons for this repository",
                    "refresh_overlays.ico", 0},
    {"userconf",    "Global Settings",
                    "Configure user wide settings",
                    "settings_user.ico", 0},
    {"repoconf",    "Repository Settings",
                    "Configure repository settings",
                    "settings_repo.ico", 0},
    {"about",       "About...",
                    "Show About Dialog",
                    "menuabout.ico", 0},
    {"datamine",    "Annotate Files",
                    "Changeset information per file line",
                    "menublame.ico", 0},
    {"vdiff",       "Visual Diff",
                    "View changes using GUI diff tool",
                    "TortoiseMerge.ico", 0},

    /* Add new items here */

    // template
    {"", "", "", ".ico", 0},
};

/* These enumerations must match the order of menuDescList */
enum menuDescListEntries
{
    Commit, Init, Clone, Status, Shelve, Add, Revert, Remove, Rename,
    Log, Synch, Serve, Update, Recover, Thgstatus, Userconf, Repoconf,
    About, Datamine, VDiff,
    /* Add new items here */
    Separator, EndOfList
};

menuDescListEntries RepoNoFilesMenu[] =
{
    Commit, Status, Shelve, VDiff, Separator,
    Log, Separator,
    Update, Separator,
    Synch, Clone, Recover, Serve, Thgstatus, Separator,
    Repoconf, Userconf, Separator,
    About, EndOfList
};

menuDescListEntries RepoFilesMenu[] =
{
    Commit, Status, VDiff, Add, Revert, Rename, Remove, Separator,
    Log, Datamine, Separator,
    About, EndOfList
};

menuDescListEntries NoRepoMenu[] =
{
    Clone, Init, Userconf, Thgstatus, Separator,
    About, EndOfList
};

typedef std::map<std::string, MenuDescription> MenuDescriptionMap;
typedef std::map<UINT, MenuDescription> MenuIdCmdMap;

MenuDescriptionMap MenuDescMap;
MenuIdCmdMap MenuIdMap;


void AddMenuList(UINT idCmd, const std::string& name)
{
    TDEBUG_TRACE("AddMenuList: idCmd = " << idCmd << " name = " << name);
    MenuIdMap[idCmd] = MenuDescMap[name];
}


void GetCMenuTranslation(
    const std::string& lang,
    const std::string& name,
    std::string& menuText,
    std::string& helpText
)
{
    std::string subkey = "Software\\TortoiseHg\\CMenu\\";
    subkey += lang;
    subkey += "\\";
    subkey += name;

    TDEBUG_TRACE("GetCMenuTranslation: " << subkey);

    HKEY hkey = 0;
    LONG rv = RegOpenKeyExA(
        HKEY_CURRENT_USER, subkey.c_str(), 0, KEY_READ, &hkey);

    if (rv == ERROR_SUCCESS && hkey)
    {
        GetRegSZValue(hkey, "menuText", menuText);
        GetRegSZValue(hkey, "helpText", helpText);
    }
    else
    {
        TDEBUG_TRACE("GetCMenuTranslation: RegOpenKeyExA(" << subkey << ") failed");
    }

    if (hkey)
        RegCloseKey(hkey);
}


void InitMenuMaps()
{
    if (MenuDescMap.empty())
    {
        std::string lang;
        GetRegistryConfig("CMenuLang", lang);

        std::size_t sz = sizeof(menuDescList) / sizeof(MenuDescription);
        for (std::size_t i = 0; i < sz; i++)
        {
            MenuDescription md = menuDescList[i];
            TDEBUG_TRACE("InitMenuMaps: adding " << md.name);

            // Look for translation of menu and help text
            if( lang.size() )
                GetCMenuTranslation(lang, md.name, md.menuText, md.helpText);

            MenuDescMap[md.name] = md;
        }
    }

    MenuIdMap.clear();
}


void InsertMenuItemWithIcon(
    HMENU hMenu, UINT indexMenu, UINT idCmd,
    const std::string& menuText, const std::string& iconName)
{
    MENUITEMINFO mi;
    mi.cbSize = sizeof(mi);
    mi.dwTypeData = const_cast<char*>(menuText.c_str());
    mi.cch = static_cast<UINT>(menuText.length());
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


void InsertSubMenuItemWithIcon(
    HMENU hMenu, HMENU hSubMenu, UINT indexMenu, UINT idCmd,
    const std::string& menuText, const std::string& iconName)
{
    MENUITEMINFO mi;
    mi.cbSize = sizeof(mi);
    mi.fMask = MIIM_SUBMENU | MIIM_STRING | MIIM_ID;
    mi.fType = MFT_STRING;
    mi.dwTypeData = const_cast<char*>(menuText.c_str());
    mi.cch = static_cast<UINT>(menuText.length());
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


void InsertMenuItemByName(
    HMENU hMenu, const std::string& name, UINT indexMenu,
    UINT idCmd, UINT idCmdFirst, const std::string& prefix)
{
    MenuDescriptionMap::iterator iter = MenuDescMap.find(name);
    if (iter == MenuDescMap.end())
    {
        TDEBUG_TRACE("InsertMenuItemByName: can't find menu info for " << name);
        return;
    }

    MenuDescription md = iter->second;
    AddMenuList(idCmd - idCmdFirst, name);
    InsertMenuItemWithIcon(
        hMenu, indexMenu, idCmd, prefix + md.menuText, md.iconName);
}


#define ResultFromShort(i)  ResultFromScode(MAKE_SCODE(SEVERITY_SUCCESS, 0, (USHORT)(i)))

// IContextMenu
STDMETHODIMP
CShellExt::QueryContextMenu(
    HMENU hMenu, UINT indexMenu, UINT idCmdFirst, UINT idCmdLast, UINT uFlags)
{
    TDEBUG_TRACE("CShellExt::QueryContextMenu");
    InitMenuMaps();

    UINT idCmd = idCmdFirst;
    BOOL bAppendItems = TRUE;

    if ((uFlags & 0x000F) == CMF_NORMAL)
        bAppendItems = TRUE;
    else if (uFlags & CMF_VERBSONLY)
        bAppendItems = TRUE;
    else if (uFlags & CMF_EXPLORE)
        bAppendItems = TRUE;
    else
        bAppendItems = FALSE;

    if (!bAppendItems)
        return NOERROR;

    const std::size_t sz = sizeof(menuDescList) / sizeof(MenuDescription);
    bool promoted[sz];
    memset(&promoted, 0, sizeof(promoted));

    std::string cval = "commit"; // default value if key not found
    GetRegistryConfig("PromotedItems", cval);

    size_t found;
    do
    {
        if (cval.empty())
            break;

        found = cval.find_first_of(',');

        std::string key;
        if( found == std::string::npos )
            key = cval;
        else
        {
            key = cval.substr(0, found);
            cval = cval.substr(found+1);
        }

        for (UINT i = 0; i < sz; i++)
        {
            if (!key.compare(menuDescList[i].name))
            {
                promoted[i] = true;
                break;
            }
        }
    }
    while (found != std::string::npos);

    // check if target directory is a Mercurial repository
    std::string cwd;
    if (!myFolder.empty())
    {
        cwd = myFolder;
    }
    else if (myFiles.size() == 1 && IsDirectory(myFiles[0]))
    {
        myFolder = myFiles[0];
        cwd = myFolder;
        myFiles.clear();
    }
    else if (!myFiles.empty())
    {
        cwd = IsDirectory(myFiles[0])? myFiles[0] : DirName(myFiles[0]);
    }
    bool isHgrepo = false;
    if (!cwd.empty())
        isHgrepo = IsHgRepo(cwd);

    /* We have three menu types: files-selected, no-files-selected, no-repo */
    menuDescListEntries *entries;
    if (isHgrepo)
        if (myFiles.empty())
            entries = RepoNoFilesMenu;
        else
            entries = RepoFilesMenu;
    else
        entries = NoRepoMenu;

    // start building TortoiseHg menus and submenus
    InsertMenu(hMenu, indexMenu++, MF_SEPARATOR | MF_BYPOSITION, 0, NULL);

    menuDescListEntries *walk;
    for (walk = entries; *walk != EndOfList; walk++)
    {
        UINT idx = (UINT) *walk;
        if (promoted[idx])
        {
            InsertMenuItemByName(
                hMenu, menuDescList[idx].name, indexMenu++,
                idCmd++, idCmdFirst, "HG "
            );
        }
    }

    const HMENU hSubMenu = CreatePopupMenu();
    if (hSubMenu)
    {
        UINT indexSubMenu = 0;
        bool isSeparator = true;
        for (walk = entries; *walk != EndOfList; walk++)
        {
            if (*walk == Separator)
            {
                if (!isSeparator)
                {
                    InsertMenu(
                        hSubMenu, indexSubMenu++,
                        MF_SEPARATOR | MF_BYPOSITION, 0, NULL
                    );
                    isSeparator = true;
                }
            }
            else
            {
                UINT idx = (UINT) *walk;
                if (!promoted[idx])
                {
                    InsertMenuItemByName(
                        hSubMenu, menuDescList[idx].name,
                        indexSubMenu++, idCmd++, idCmdFirst, ""
                    );
                    isSeparator = false;
                }
            }
        }
        if (isSeparator && indexSubMenu > 0)
            RemoveMenu(hSubMenu, indexSubMenu - 1, MF_BYPOSITION);
    }

    TDEBUG_TRACE("  CShellExt::QueryContextMenu: adding main THG menu");
    InsertSubMenuItemWithIcon(hMenu, hSubMenu, indexMenu++, idCmd++,
            "TortoiseHG...", "hg.ico");

    InsertMenu(hMenu, indexMenu++, MF_SEPARATOR | MF_BYPOSITION, 0, NULL);

    InitStatus::check();
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
        if (iter != MenuIdMap.end())
        {
            DoHgtk(iter->second.name);
            hr = NOERROR;
        }
        else
        {
            TDEBUG_TRACE(
                "CShellExt::InvokeCommand: action not found for idCmd "
                << idCmd
            );
        }
    }
    return hr;
}


STDMETHODIMP
CShellExt::GetCommandString(
    UINT_PTR idCmd, UINT uFlags, UINT FAR *reserved,
    LPSTR pszName, UINT cchMax)
{
    // see http://msdn.microsoft.com/en-us/library/bb776094%28VS.85%29.aspx

    HRESULT res = S_FALSE;

    const char *psz = "";

    std::string sflags = "?";
    switch (uFlags)
    {
    case GCS_HELPTEXTW:
        sflags = "GCS_HELPTEXTW"; break;
    case GCS_HELPTEXTA:
        sflags = "GCS_HELPTEXTA"; break;
    case GCS_VALIDATEW:
        sflags = "GCS_VALIDATEW"; break;
    case GCS_VALIDATEA:
        sflags = "GCS_VALIDATEA"; break;
    case GCS_VERBW:
        sflags = "GCS_VERBW"; break;
    case GCS_VERBA:
        sflags = "GCS_VERBA"; break;
    }

    TDEBUG_TRACE(
        "CShellExt::GetCommandString: idCmd = " << idCmd 
        << ", uFlags = " << uFlags << " (" << sflags << ")"
        << ", cchMax = " << cchMax
    );

    MenuIdCmdMap::iterator iter = MenuIdMap.find(static_cast<UINT>(idCmd));
    if (iter == MenuIdMap.end())
    {
        TDEBUG_TRACE("CShellExt::GetCommandString: idCmd not found");
    }
    else
    {
        TDEBUG_TRACE(
            "CShellExt::GetCommandString: name = \"" << iter->second.name << "\"");

        if (uFlags == GCS_HELPTEXTW || uFlags == GCS_HELPTEXTA)
        {
            psz = iter->second.helpText.c_str();
            res = S_OK;
            
            size_t size = iter->second.helpText.size();
            if (size >= 40)
            {
                TDEBUG_TRACE(
                    "CShellExt::GetCommandString: warning:" 
                    << " length of help text is " << size
                    << ", which is not reasonably short (<40)");
            }
        }
        else if (uFlags == GCS_VERBW || uFlags == GCS_VERBA)
        {
            psz = iter->second.name.c_str();
            res = S_OK;
        }
        else if (uFlags == GCS_VALIDATEW || uFlags == GCS_VALIDATEA)
        {
            res = S_OK;
        }
    }

    if (cchMax < 1)
    {
        TDEBUG_TRACE("CShellExt::GetCommandString: cchMax = " 
            << cchMax << " (is <1)");
        return res;
    }

    size_t size = 0;

    if (uFlags & GCS_UNICODE)
    {
        wchar_t* const dest = reinterpret_cast<wchar_t*>(pszName);
        const wchar_t* const src = _WCSTR(psz);

        wcsncpy(dest, src, cchMax-1);
        *(dest + cchMax-1) = 0;

        size = wcslen(src);
    }
    else
    {
        strncpy(pszName, psz, cchMax-1);
        *(pszName + cchMax-1) = 0;

        size = strlen(psz);
    }

    TDEBUG_TRACE("CShellExt::GetCommandString: res = " << res 
        << ", pszName = \"" << psz << "\"");

    if (size > cchMax-1)
    {
        TDEBUG_TRACE(
            "CShellExt::GetCommandString: string was truncated: size = "
                << size << ", cchMax = " << cchMax);
    }

    return res;
}


STDMETHODIMP
CShellExt::HandleMenuMsg(UINT uMsg, WPARAM wParam, LPARAM lParam)
{
    LRESULT res;
    return HandleMenuMsg2(uMsg, wParam, lParam, &res);
}


STDMETHODIMP
CShellExt::HandleMenuMsg2(
    UINT uMsg, WPARAM wParam, LPARAM lParam, LRESULT* pResult)
{
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
            DrawIconEx(
                lpdis->hDC,
                lpdis->rcItem.left - 16,
                lpdis->rcItem.top
                    + (lpdis->rcItem.bottom - lpdis->rcItem.top - 16) / 2,
                (HICON) lpdis->itemData, 16, 16,
                0, 0, DI_NORMAL
            );
            *pResult = TRUE;
        }
        break;

    default:
        return NOERROR;
    }

    return NOERROR;
}


void CShellExt::DoHgtk(const std::string &cmd)
{
    std::string dir = GetTHgProgRoot();
    if (dir.empty())
    {
        TDEBUG_TRACE("DoHgtk: THG root is empty");
        return;
    }
    std::string hgcmd = dir + "\\hgtk.exe";

    WIN32_FIND_DATAA data;
    HANDLE hfind = FindFirstFileA(hgcmd.c_str(), &data);
    if (hfind == INVALID_HANDLE_VALUE)
        hgcmd = dir + "\\hgtk.cmd";
    else
        FindClose(hfind);

    hgcmd = Quote(hgcmd) + " --nofork " + cmd;

    std::string cwd;
    if (!myFolder.empty())
    {
        cwd = myFolder;
    }
    else if (myFiles.size() == 1 && IsDirectory(myFiles[0]))
    {
        // Treat single selected directory as if cmenu were opened
        // within that directory without files selected
        cwd = myFiles[0];
    }
    else if (!myFiles.empty())
    {
        cwd = IsDirectory(myFiles[0])? myFiles[0] : DirName(myFiles[0]);

        const std::string tempfile = GetTemporaryFile();
        if (tempfile.empty())
        {
            TDEBUG_TRACE("DoHgtk: error: GetTemporaryFile returned empty string");
            return;
        }

        TDEBUG_TRACE("DoHgtk: temp file = " << tempfile);
        HANDLE tempfileHandle = CreateFileA(
            tempfile.c_str(), GENERIC_WRITE,
            FILE_SHARE_READ, 0, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, 0
        );

        if (tempfileHandle == INVALID_HANDLE_VALUE)
        {
            TDEBUG_TRACE("DoHgtk: error: failed to create file " << tempfile);
            return;
        }

        typedef std::vector<std::string>::size_type ST;
        for (ST i = 0; i < myFiles.size(); i++)
        {
            DWORD dwWritten;
            TDEBUG_TRACE("DoHgtk: temp file adding " << myFiles[i]);
            WriteFile(
                tempfileHandle, myFiles[i].c_str(),
                static_cast<DWORD>(myFiles[i].size()), &dwWritten, 0
            );
            WriteFile(tempfileHandle, "\n", 1, &dwWritten, 0);
        }
        CloseHandle(tempfileHandle);
        hgcmd += " --listfile " + Quote(tempfile);
    }
    else
    {
        TDEBUG_TRACE("DoHgtk: can't get cwd");
        return;
    }

    if (cmd == "thgstatus")
    {
        Thgstatus::remove(cwd);
        InitStatus::check();
        return;
    }

    LaunchCommand(hgcmd, cwd);
    InitStatus::check();
}
