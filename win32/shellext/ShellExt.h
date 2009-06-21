#ifndef _SHELL_EXT_H_
#define _SHELL_EXT_H_

#include <vector>
#include <string>


enum TortoiseOLEClass
{
   TORTOISE_OLE_INVALID,
   TORTOISE_OLE_ADDED,
   TORTOISE_OLE_MODIFIED,
   TORTOISE_OLE_UNCHANGED,
   TORTOISE_OLE_IGNORED,
   TORTOISE_OLE_NOTINREPO,
};


class CDllRegSxClassFactory: public IClassFactory
{
    protected:
        ULONG m_cRef;
        TortoiseOLEClass myclassToMake;

    public:
        CDllRegSxClassFactory(TortoiseOLEClass);
        ~CDllRegSxClassFactory();

        static LPCRITICAL_SECTION GetCriticalSection();

        STDMETHODIMP QueryInterface(REFIID, LPVOID FAR*);
        STDMETHODIMP_(ULONG) AddRef();
        STDMETHODIMP_(ULONG) Release();

        STDMETHODIMP CreateInstance(LPUNKNOWN, REFIID, LPVOID FAR*);
        STDMETHODIMP LockServer(BOOL);
};

typedef CDllRegSxClassFactory* LPCSHELLEXTCLASSFACTORY;


class CShellExt: 
    public IContextMenu3, IShellIconOverlayIdentifier, IShellExtInit
{
    TortoiseOLEClass myTortoiseClass;
    
    protected:
        ULONG m_cRef;
        LPDATAOBJECT m_pDataObj;

        LPTSTR* m_ppszFileUserClickedOn; // [MAX_PATH]
        std::vector<std::string> myFiles;
        std::string myFolder;

        void CShellExt::DoHgtk(const std::string&);

    public:
        static LPCRITICAL_SECTION GetCriticalSection();

        CShellExt(TortoiseOLEClass);
        ~CShellExt();

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

        // IShellIconOverlayIdentifier
        STDMETHODIMP GetOverlayInfo(
            LPWSTR pwszIconFile, int cchMax, int* pIndex, DWORD* pdwFlags);
        STDMETHODIMP GetPriority(int* pPriority);
        STDMETHODIMP IsMemberOf(LPCWSTR pwszPath, DWORD dwAttrib);

        // IShellExtInit
        STDMETHODIMP Initialize(
            LPCITEMIDLIST pIDFolder, LPDATAOBJECT pDataObj, HKEY hKeyID);
    };

typedef CShellExt* LPCSHELLEXT;


class ThgCriticalSection
{
    LPCRITICAL_SECTION cs_;

public:
    ThgCriticalSection(LPCRITICAL_SECTION cs): cs_(cs)
    {
        ::EnterCriticalSection(cs_);
    }

    ~ThgCriticalSection()
    {
        ::LeaveCriticalSection(cs_);
    }
};


#endif // _SHELL_EXT_H_
