#include "stdafx.h"
#include "ShellExt.h"
#include "TortoiseUtils.h"
#include "StringUtils.h"
#include "InitStatus.h"
#include "ThgClassFactory.h"
#include "CShellExtCMenu.h"
#include "CShellExtOverlay.h"


#define CLSID_TortoiseHgCmenu L"{46605027-5B8C-4DCE-BFE0-051B7972D64C}"
#define CLSID_TortoiseHg0     L"{869C8877-2C3C-438D-844B-31B86BFE5E8A}"
#define CLSID_TortoiseHg1     L"{AF42ADAB-8C2E-4285-B746-99B31094708E}"
#define CLSID_TortoiseHg2     L"{CDA1C89D-E9B5-4981-A857-82DD932EA2FD}"
#define CLSID_TortoiseHg6     L"{9E3D4EC9-0624-4393-8B48-204C217ED1FF}"


UINT g_cRefThisDll = 0;
HINSTANCE g_hmodThisDll = NULL;

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
    std::wstring clsid;
    {
        LPWSTR ptr = 0;
        ::StringFromIID(rclsid, &ptr);
        clsid = ptr;
        ::CoTaskMemFree(ptr);
    }

    TDEBUG_TRACEW("DllGetClassObject clsid = " << clsid);

    if (ppvOut == 0)
    {
        TDEBUG_TRACE("**** DllGetClassObject: error: ppvOut is 0");
        return E_POINTER;
    }

    *ppvOut = NULL;

    typedef ThgClassFactory<CShellExtOverlay> FactOvl;
    typedef ThgClassFactory<CShellExtCMenu>   FactCmenu;

    if (clsid == CLSID_TortoiseHgCmenu)
    {
        FactCmenu *pcf = new FactCmenu(0);
        TDEBUG_TRACE("DllGetClassObject clsname = " << "CLSID_TortoiseHgCmenu");
        return pcf->QueryInterface(riid, ppvOut);
    }
    else if (clsid == CLSID_TortoiseHg0)
    {
        FactOvl *pcf = new FactOvl('C');  // clean
        TDEBUG_TRACE("DllGetClassObject clsname = " << "CLSID_TortoiseHg0");
        ++InitStatus::inst().unchanged_;
        return pcf->QueryInterface(riid, ppvOut);
    }
    else if (clsid == CLSID_TortoiseHg1)
    {
        FactOvl *pcf = new FactOvl('A');  // added
        TDEBUG_TRACE("DllGetClassObject clsname = " << "CLSID_TortoiseHg1");
        ++InitStatus::inst().added_;
        return pcf->QueryInterface(riid, ppvOut);
    }
    else if (clsid == CLSID_TortoiseHg2)
    {
        FactOvl *pcf = new FactOvl('M');   // modified
        TDEBUG_TRACE("DllGetClassObject clsname = " << "CLSID_TortoiseHg2");
        ++InitStatus::inst().modified_;
        return pcf->QueryInterface(riid, ppvOut);
    }
    else if (clsid == CLSID_TortoiseHg6)
    {
        FactOvl *pcf = new FactOvl('?');   // not in repo
        TDEBUG_TRACE("DllGetClassObject clsname = " << "CLSID_TortoiseHg6");
        ++InitStatus::inst().notinrepo_;
        return pcf->QueryInterface(riid, ppvOut);
    }

    return CLASS_E_CLASSNOTAVAILABLE;
}


VOID _LoadResources(VOID)
{
}


VOID _UnloadResources(VOID)
{
}


LPCRITICAL_SECTION CShellExt::GetCriticalSection()
{
    return &g_critical_section;
}


void CShellExt::IncDllRef()
{
    ThgCriticalSection cs(CShellExt::GetCriticalSection());
    g_cRefThisDll++;
}


void CShellExt::DecDllRef()
{
    ThgCriticalSection cs(CShellExt::GetCriticalSection());
    g_cRefThisDll--;
}
