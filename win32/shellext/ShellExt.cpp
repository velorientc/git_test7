#include "stdafx.h"
#include "ShellExt.h"
#include "TortoiseUtils.h"
#include "ShellUtils.h"
#include "StringUtils.h"
#include <olectl.h>

#define INITGUID
#include <initguid.h>

DEFINE_GUID(CLSID_TortoiseHg0, 0xb456dba0L, 0x7bf4, 0x478c, 0x93, 0x7a, 0x5, 0x13, 0xc, 0x2c, 0x21, 0x2e);
DEFINE_GUID(CLSID_TortoiseHg1, 0xb456dba1L, 0x7bf4, 0x478c, 0x93, 0x7a, 0x5, 0x13, 0xc, 0x2c, 0x21, 0x2e);
DEFINE_GUID(CLSID_TortoiseHg2, 0xb456dba2L, 0x7bf4, 0x478c, 0x93, 0x7a, 0x5, 0x13, 0xc, 0x2c, 0x21, 0x2e);
DEFINE_GUID(CLSID_TortoiseHg3, 0xb456dba3L, 0x7bf4, 0x478c, 0x93, 0x7a, 0x5, 0x13, 0xc, 0x2c, 0x21, 0x2e);
DEFINE_GUID(CLSID_TortoiseHg4, 0xb456dba4L, 0x7bf4, 0x478c, 0x93, 0x7a, 0x5, 0x13, 0xc, 0x2c, 0x21, 0x2e);
DEFINE_GUID(CLSID_TortoiseHg5, 0xb456dba5L, 0x7bf4, 0x478c, 0x93, 0x7a, 0x5, 0x13, 0xc, 0x2c, 0x21, 0x2e);
DEFINE_GUID(CLSID_TortoiseHg6, 0xb456dba6L, 0x7bf4, 0x478c, 0x93, 0x7a, 0x5, 0x13, 0xc, 0x2c, 0x21, 0x2e);

UINT g_cRefThisDll = 0;
HINSTANCE g_hmodThisDll = NULL;

HMENU hSubMenu = 0;

CRITICAL_SECTION g_critical_section;


typedef struct
{
   HKEY  hRootKey;
   LPTSTR lpszSubKey;
   LPTSTR lpszValueName;
   LPTSTR lpszData;
} REGSTRUCT, *LPREGSTRUCT;


VOID _LoadResources();
VOID _UnloadResources();


extern "C" 
int APIENTRY DllMain(HINSTANCE hInstance, DWORD dwReason, LPVOID lpReserved)
{
    TDEBUG_TRACE("DllMain");

    if (dwReason == DLL_PROCESS_ATTACH)
    {
        TDEBUG_TRACE("DllMain: DLL_PROCESS_ATTACH");
        g_hmodThisDll = hInstance;
        ::InitializeCriticalSection(&g_critical_section);
        _LoadResources();
    }
    else if (dwReason == DLL_PROCESS_DETACH)
    {
        TDEBUG_TRACE("DllMain: DLL_PROCESS_ATTACH");
        ::DeleteCriticalSection(&g_critical_section);
        _UnloadResources();
    }

    return 1;
}


STDAPI DllCanUnloadNow(void)
{
    TDEBUG_TRACE("DllCanUnloadNow");
    return (g_cRefThisDll == 0 ? S_OK : S_FALSE);
}


STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, LPVOID *ppvOut)
{
    LPWSTR   pwszShellExt;
    StringFromIID(rclsid, &pwszShellExt);
    TDEBUG_TRACE("DllGetClassObject clsid = " << WideToMultibyte(pwszShellExt));
    *ppvOut = NULL;

    if (IsEqualIID(rclsid, CLSID_TortoiseHg0))
    {
        CDllRegSxClassFactory *pcf =
            new CDllRegSxClassFactory(TORTOISE_OLE_UNCHANGED);
        TDEBUG_TRACE("DllGetClassObject clsname = " << "CLSID_TortoiseHg0");
        return pcf->QueryInterface(riid, ppvOut);
    }
    else if (IsEqualIID(rclsid, CLSID_TortoiseHg1))
    {
        CDllRegSxClassFactory *pcf =
            new CDllRegSxClassFactory(TORTOISE_OLE_ADDED);
        TDEBUG_TRACE("DllGetClassObject clsname = " << "CLSID_TortoiseHg1");
        return pcf->QueryInterface(riid, ppvOut);
    }
    else if (IsEqualIID(rclsid, CLSID_TortoiseHg2))
    {
        CDllRegSxClassFactory *pcf =
            new CDllRegSxClassFactory(TORTOISE_OLE_MODIFIED);
        TDEBUG_TRACE("DllGetClassObject clsname = " << "CLSID_TortoiseHg2");
        return pcf->QueryInterface(riid, ppvOut);
    }
    else if (IsEqualIID(rclsid, CLSID_TortoiseHg6))
    {
        CDllRegSxClassFactory *pcf =
            new CDllRegSxClassFactory(TORTOISE_OLE_NOTINREPO);
        TDEBUG_TRACE("DllGetClassObject clsname = " << "CLSID_TortoiseHg6");
        return pcf->QueryInterface(riid, ppvOut);
    }

    return CLASS_E_CLASSNOTAVAILABLE;
}


VOID _LoadResources(VOID)
{
}


VOID _UnloadResources(VOID)
{
    if (hSubMenu)
        DestroyMenu(hSubMenu);
}


LPCRITICAL_SECTION CDllRegSxClassFactory::GetCriticalSection()
{
    return &g_critical_section;
}


CDllRegSxClassFactory::CDllRegSxClassFactory(TortoiseOLEClass classToMake)
{
    ThgCriticalSection cs(GetCriticalSection());
    m_cRef = 0L;
    g_cRefThisDll++;
    myclassToMake = classToMake;
}


CDllRegSxClassFactory::~CDllRegSxClassFactory()
{
    ThgCriticalSection cs(GetCriticalSection());
    g_cRefThisDll--;
}


STDMETHODIMP CDllRegSxClassFactory::QueryInterface(
    REFIID riid, LPVOID FAR* ppv)
{
    *ppv = NULL;

    if (IsEqualIID(riid, IID_IUnknown) || IsEqualIID(riid, IID_IClassFactory))
    {
        *ppv = (LPCLASSFACTORY) this;
        AddRef();
        return NOERROR;
    }

    return E_NOINTERFACE;
}


STDMETHODIMP_(ULONG) CDllRegSxClassFactory::AddRef()
{
    ThgCriticalSection cs(GetCriticalSection());
    return ++m_cRef;
}


STDMETHODIMP_(ULONG) CDllRegSxClassFactory::Release()
{
    ThgCriticalSection cs(GetCriticalSection());
    if (--m_cRef)
        return m_cRef;

    delete this;
    return 0L;
}


STDMETHODIMP CDllRegSxClassFactory::CreateInstance(
    LPUNKNOWN pUnkOuter, REFIID riid, LPVOID* ppvObj)
{
    *ppvObj = NULL;

    if (pUnkOuter)
        return CLASS_E_NOAGGREGATION;

    LPCSHELLEXT pShellExt = new CShellExt(myclassToMake);
    if (NULL == pShellExt)
        return E_OUTOFMEMORY;

    return pShellExt->QueryInterface(riid, ppvObj);
}


STDMETHODIMP CDllRegSxClassFactory::LockServer(BOOL fLock)
{
    return NOERROR;
}


CShellExt::CShellExt(TortoiseOLEClass tortoiseClass)
    : m_ppszFileUserClickedOn(0)
{
    ThgCriticalSection cs(GetCriticalSection());

    myTortoiseClass = tortoiseClass;
    m_cRef = 0L;
    m_pDataObj = NULL;

    g_cRefThisDll++;
}


CShellExt::~CShellExt()
{
    ThgCriticalSection cs(GetCriticalSection());

    if (m_pDataObj)
        m_pDataObj->Release();

    g_cRefThisDll--;
}


LPCRITICAL_SECTION CShellExt::GetCriticalSection()
{
    return &g_critical_section;
}


STDMETHODIMP CShellExt::QueryInterface(REFIID riid, LPVOID FAR* ppv)
{
    std::string clsname = "UNKNOWN CLSID";
    
    *ppv = NULL;
    if (IsEqualIID(riid, IID_IShellExtInit) || IsEqualIID(riid, IID_IUnknown))
    {
        *ppv = (LPSHELLEXTINIT)this;
        clsname = "IID_IShellExtInit";
    }
    else if (IsEqualIID(riid, IID_IContextMenu))
    {
        *ppv = (LPCONTEXTMENU)this;
        clsname = "IID_IContextMenu";
    }
    else if (IsEqualIID(riid, IID_IContextMenu2))
    {
        *ppv = (IContextMenu2 *) this;
        clsname = "IID_IContextMenu2";
    }
    else if (IsEqualIID(riid, IID_IContextMenu3))
    {
        *ppv = (IContextMenu3 *) this;
        clsname = "IID_IContextMenu3";
    }
    else if (IsEqualIID(riid, IID_IShellIconOverlayIdentifier))
    {
        *ppv = (IShellIconOverlayIdentifier *) this;
        clsname = "IID_IShellIconOverlayIdentifier";
    }

    TDEBUG_TRACE("CShellExt::QueryInterface: " << clsname);
    
    if (*ppv)
    {
        AddRef();
        return NOERROR;
    }

    return E_NOINTERFACE;
}


STDMETHODIMP_(ULONG) CShellExt::AddRef()
{
    ThgCriticalSection cs(GetCriticalSection());
    return ++m_cRef;
}


STDMETHODIMP_(ULONG) CShellExt::Release()
{
    ThgCriticalSection cs(GetCriticalSection());

    if(--m_cRef)
        return m_cRef;

    delete this;
    return 0L;
}


STDMETHODIMP CShellExt::Initialize(
    LPCITEMIDLIST pIDFolder, LPDATAOBJECT pDataObj, HKEY hRegKey)
{
    TCHAR name[MAX_PATH+1];

    TDEBUG_TRACE("CShellExt::Initialize");
    TDEBUG_TRACE("  pIDFolder: " << pIDFolder);
    TDEBUG_TRACE("  pDataObj: " << pDataObj);

    myFolder.clear();
    myFiles.clear();

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

    // if a directory background
    if (pIDFolder) 
    {
        SHGetPathFromIDList(pIDFolder, name);
        TDEBUG_TRACE("  Folder " << name);
        myFolder = name;
    }

    return NOERROR;
}
