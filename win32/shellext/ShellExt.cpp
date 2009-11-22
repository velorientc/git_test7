#include "stdafx.h"
#include "ShellExt.h"
#include "TortoiseUtils.h"
#include "StringUtils.h"
#include "InitStatus.h"
#include "ThgClassFactory.h"
#include "CShellExtCMenu.h"
#include "CShellExtOverlay.h"

#include <olectl.h>

#define INITGUID
#include <initguid.h>

DEFINE_GUID(CLSID_TortoiseHgCmenu, 0xb456db9fL, 0x7bf4, 0x478c, 0x93, 0x7a, 0x5, 0x13, 0xc, 0x2c, 0x21, 0x2e);

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

    if (g_cRefThisDll > 0)
        InitStatus::check();

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

    typedef ThgClassFactory<CShellExtOverlay> FactOvl;
    typedef ThgClassFactory<CShellExtCMenu>   FactCmenu;

    if (IsEqualIID(rclsid, CLSID_TortoiseHgCmenu))
    {
        FactCmenu *pcf = new FactCmenu(0);
        TDEBUG_TRACE("DllGetClassObject clsname = " << "CLSID_TortoiseHgCmenu");
        return pcf->QueryInterface(riid, ppvOut);
    }
    else if (IsEqualIID(rclsid, CLSID_TortoiseHg0))
    {
        FactOvl *pcf = new FactOvl('C');  // clean
        TDEBUG_TRACE("DllGetClassObject clsname = " << "CLSID_TortoiseHg0");
        ++InitStatus::inst().unchanged_;
        return pcf->QueryInterface(riid, ppvOut);
    }
    else if (IsEqualIID(rclsid, CLSID_TortoiseHg1))
    {
        FactOvl *pcf = new FactOvl('A');  // added
        TDEBUG_TRACE("DllGetClassObject clsname = " << "CLSID_TortoiseHg1");
        ++InitStatus::inst().added_;
        return pcf->QueryInterface(riid, ppvOut);
    }
    else if (IsEqualIID(rclsid, CLSID_TortoiseHg2))
    {
        FactOvl *pcf = new FactOvl('M');   // modified
        TDEBUG_TRACE("DllGetClassObject clsname = " << "CLSID_TortoiseHg2");
        ++InitStatus::inst().modified_;
        return pcf->QueryInterface(riid, ppvOut);
    }
    else if (IsEqualIID(rclsid, CLSID_TortoiseHg6))
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
    if (hSubMenu)
        DestroyMenu(hSubMenu);
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
