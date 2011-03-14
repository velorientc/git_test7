#ifndef _CShellExtCMenu_h_
#define _CShellExtCMenu_h_

#include <vector>
#include <string>
#include <map>

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


class CShellExtCMenu: public IContextMenu3, IShellExtInit
{

protected:
    ULONG m_cRef;
    std::vector<std::string> myFiles;
    std::string myFolder;
    MenuDescriptionMap CMenuMenuDescMap;
    MenuIdCmdMap MenuIdMap;

    virtual void RunDialog(const std::string&);
    virtual MenuDescriptionMap& GetMenuDescriptionMap();

    void TweakMenuForVista(HMENU menu);
    void PrintDebugHeader(LPCITEMIDLIST pIDFolder, LPDATAOBJECT pDataObj);
    void InitMenuMaps(MenuDescription *menuDescs, std::size_t sz);
    void InsertMenuItemByName(
	    HMENU hMenu, const std::string& name, UINT indexMenu,
	    UINT idCmd, UINT idCmdFirst, const std::wstring& prefix);
    void AddMenuList(UINT idCmd, const std::string& name,
      MenuDescriptionMap& menuDescMap);

public:
    explicit CShellExtCMenu(const char dummy);
    ~CShellExtCMenu();

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, LPVOID FAR *ppv);
    STDMETHODIMP_(ULONG) AddRef();
    STDMETHODIMP_(ULONG) Release();

    // IContextMenu3
    STDMETHODIMP QueryContextMenu(
        HMENU hMenu, UINT indexMenu, UINT idCmdFirst, UINT idCmdLast,
        UINT uFlags);
    STDMETHODIMP InvokeCommand(LPCMINVOKECOMMANDINFO lpcmi);
    STDMETHODIMP GetCommandString(
        UINT_PTR idCmd, UINT uFlags, UINT FAR* reserved,LPSTR pszName,
        UINT cchMax);
    STDMETHODIMP HandleMenuMsg(UINT uMsg, WPARAM wParam, LPARAM lParam);
    STDMETHODIMP HandleMenuMsg2(
        UINT uMsg, WPARAM wParam, LPARAM lParam, LRESULT* pResult);

    // IShellExtInit
    STDMETHODIMP Initialize(
        LPCITEMIDLIST pIDFolder, LPDATAOBJECT pDataObj, HKEY hKeyID);
};


#endif
