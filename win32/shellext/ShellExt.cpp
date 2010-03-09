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

DEFINE_GUID(CLSID_TortoiseHgCmenu, 0x46605027L, 0x5B8C, 0x4DCE, 0xBF, 0xE0, 0x05, 0x1B, 0x79, 0x72, 0xD6, 0x4C);

DEFINE_GUID(CLSID_TortoiseHg0, 0x869C8877L, 0x2C3C, 0x438D, 0x84, 0x4B, 0x31, 0xB8, 0x6B, 0xFE, 0x5E, 0x8A);
DEFINE_GUID(CLSID_TortoiseHg1, 0xAF42ADABL, 0x8C2E, 0x4285, 0xB7, 0x46, 0x99, 0xB3, 0x10, 0x94, 0x70, 0x8E);
DEFINE_GUID(CLSID_TortoiseHg2, 0xCDA1C89DL, 0xE9B5, 0x4981, 0xA8, 0x57, 0x82, 0xDD, 0x93, 0x2E, 0xA2, 0xFD);
DEFINE_GUID(CLSID_TortoiseHg6, 0x9E3D4EC9L, 0x0624, 0x4393, 0x8B, 0x48, 0x20, 0x4C, 0x21, 0x7E, 0xD1, 0xFF);

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
    LPWSTR   pwszShellExt;
    StringFromIID(rclsid, &pwszShellExt);
    TDEBUG_TRACEW("DllGetClassObject clsid = " << pwszShellExt);

    if (ppvOut == 0)
    {
        TDEBUG_TRACE("**** DllGetClassObject: error: ppvOut is 0");
        return E_POINTER;
    }

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
