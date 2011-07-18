#ifndef _CShellExtCMenu_h_
#define _CShellExtCMenu_h_

#include <vector>
#include <string>
#include <map>

#include "SimpleUnknown.h"

struct MenuDescription
{
    std::string name;
    std::wstring menuText;
    std::wstring helpText;
    std::string iconName;
    UINT idCmd;
};

typedef std::map<std::string, MenuDescription> MenuDescriptionMap;

typedef std::map<UINT, MenuDescription> MenuIdCmdMap;


class CShellExtCMenu: public CSimpleUnknown, IContextMenu3, IShellExtInit
{

protected:
    ULONG m_cRef;
    std::vector<std::string> myFiles;
    std::string myFolder;
    MenuDescriptionMap myDescMap;
    MenuIdCmdMap myMenuIdMap;

    virtual void RunDialog(const std::string&);

    void TweakMenuForVista(HMENU menu);
    void PrintDebugHeader(LPCITEMIDLIST pIDFolder, LPDATAOBJECT pDataObj);
    void InitMenuMaps(const MenuDescription *menuDescs, std::size_t sz);
    void InsertMenuItemByName(
	    HMENU hMenu, const std::string& name, UINT indexMenu,
	    UINT idCmd, UINT idCmdFirst, const std::wstring& prefix);
    void AddMenuList(UINT idCmd, const std::string& name);

public:
    explicit CShellExtCMenu(const char dummy);
    ~CShellExtCMenu();

    DECLARE_UNKNOWN()

    // IContextMenu3
    STDMETHOD(QueryContextMenu)(
        HMENU hMenu, UINT indexMenu, UINT idCmdFirst, UINT idCmdLast,
        UINT uFlags);
    STDMETHOD(InvokeCommand)(LPCMINVOKECOMMANDINFO lpcmi);
    STDMETHOD(GetCommandString)(
        UINT_PTR idCmd, UINT uFlags, UINT FAR* reserved,LPSTR pszName,
        UINT cchMax);
    STDMETHOD(HandleMenuMsg)(UINT uMsg, WPARAM wParam, LPARAM lParam);
    STDMETHOD(HandleMenuMsg2)(
        UINT uMsg, WPARAM wParam, LPARAM lParam, LRESULT* pResult);

    // IShellExtInit
    STDMETHOD(Initialize)(
        LPCITEMIDLIST pIDFolder, LPDATAOBJECT pDataObj, HKEY hKeyID);
};


#endif
