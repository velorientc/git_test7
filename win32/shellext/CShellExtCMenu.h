#ifndef _CShellExtCMenu_h_
#define _CShellExtCMenu_h_

#include <vector>
#include <string>


class CShellExtCMenu: public IContextMenu3, IShellExtInit
{
    ULONG m_cRef;

    LPTSTR* m_ppszFileUserClickedOn; // [MAX_PATH]
    std::vector<std::string> myFiles;
    std::string myFolder;

    void DoHgtk(const std::string&);

public:
    explicit CShellExtCMenu(char dummy);
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
