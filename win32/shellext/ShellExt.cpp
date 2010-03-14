#include "stdafx.h"
#include "ShellExt.h"
#include "TortoiseUtils.h"
#include "StringUtils.h"
#include "InitStatus.h"
#include "ThgClassFactory.h"
#include "CShellExtCMenu.h"
#include "CShellExtOverlay.h"
#include "ThgCLSIDs.h"


#define TOLSTR(x)   L ## #x
#define TOLSTR2(x)  TOLSTR(x)

#define CLSID_TortoiseHgCmenu  TOLSTR2(THG_CLSID_TortoiseHgCmenu)
#define CLSID_TortoiseHgNormal       TOLSTR2(THG_CLSID_TortoiseHgNormal)
#define CLSID_TortoiseHgAdded        TOLSTR2(THG_CLSID_TortoiseHgAdded)
#define CLSID_TortoiseHgModified     TOLSTR2(THG_CLSID_TortoiseHgModified)
#define CLSID_TortoiseHgDeleted      TOLSTR2(THG_CLSID_TortoiseHgDeleted)


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
    else if (clsid == CLSID_TortoiseHgNormal)
    {
        FactOvl *pcf = new FactOvl('C');  // clean
        TDEBUG_TRACE("DllGetClassObject clsname = " << "CLSID_TortoiseHgNormal");
        ++InitStatus::inst().unchanged_;
        return pcf->QueryInterface(riid, ppvOut);
    }
    else if (clsid == CLSID_TortoiseHgAdded)
    {
        FactOvl *pcf = new FactOvl('A');  // added
        TDEBUG_TRACE("DllGetClassObject clsname = " << "CLSID_TortoiseHgAdded");
        ++InitStatus::inst().added_;
        return pcf->QueryInterface(riid, ppvOut);
    }
    else if (clsid == CLSID_TortoiseHgModified)
    {
        FactOvl *pcf = new FactOvl('M');   // modified
        TDEBUG_TRACE("DllGetClassObject clsname = " << "CLSID_TortoiseHgModified");
        ++InitStatus::inst().modified_;
        return pcf->QueryInterface(riid, ppvOut);
    }
    else if (clsid == CLSID_TortoiseHgDeleted)
    {
        FactOvl *pcf = new FactOvl('?');   // not in repo
        TDEBUG_TRACE("DllGetClassObject clsname = " << "CLSID_TortoiseHgDeleted");
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
