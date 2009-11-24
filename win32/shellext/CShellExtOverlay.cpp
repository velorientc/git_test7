#include "stdafx.h"
#include "ShellExt.h"
#include "TortoiseUtils.h"
#include "StringUtils.h"
#include "QueryDirstate.h"
#include "CShellExtOverlay.h"

#include <shlwapi.h>


STDMETHODIMP CShellExtOverlay::GetOverlayInfo(
    LPWSTR pwszIconFile, int cchMax, int *pIndex, DWORD *pdwFlags)
{
    TDEBUG_TRACE("CShellExtOverlay::GetOverlayInfo: myTortoiseClass = " << myTortoiseClass);
    // icons are determined by TortoiseOverlays shim
    *pIndex = 0;
    *pdwFlags = 0;
    *pwszIconFile = 0;
    return S_OK;
}


STDMETHODIMP CShellExtOverlay::GetPriority(int *pPriority)
{
    *pPriority = 1;
    return S_OK;
}


STDMETHODIMP CShellExtOverlay::IsMemberOf(LPCWSTR pwszPath, DWORD /* dwAttrib */)
{
    ThgCriticalSection cs(CShellExt::GetCriticalSection());

    std::string cval;
    if (GetRegistryConfig("EnableOverlays", cval) != 0 && cval == "0")
        return S_FALSE;

    std::string path = WideToMultibyte(pwszPath);

    if (GetRegistryConfig("LocalDisksOnly", cval) != 0 && cval != "0"
            && PathIsNetworkPath(path.c_str()))
        return S_FALSE;

    char filterStatus = 0;
    if (myTortoiseClass == 'A')
       filterStatus = 'A';

    char status = 0;
    if (!HgQueryDirstate(myTortoiseClass, path, filterStatus, status))
        return S_FALSE;

    if (status == myTortoiseClass)
        return S_OK;

    return S_FALSE;
}


CShellExtOverlay::CShellExtOverlay(char tortoiseClass) :
    myTortoiseClass(tortoiseClass)
{
    m_cRef = 0L;
    CShellExt::IncDllRef();
}


CShellExtOverlay::~CShellExtOverlay()
{
    CShellExt::DecDllRef();
}


STDMETHODIMP_(ULONG) CShellExtOverlay::AddRef()
{
    ThgCriticalSection cs(CShellExt::GetCriticalSection());
    return ++m_cRef;
}


STDMETHODIMP_(ULONG) CShellExtOverlay::Release()
{
    ThgCriticalSection cs(CShellExt::GetCriticalSection());
    if(--m_cRef)
        return m_cRef;
    delete this;
    return 0L;
}


STDMETHODIMP CShellExtOverlay::QueryInterface(REFIID riid, LPVOID FAR* ppv)
{    
    *ppv = NULL;
    if (IsEqualIID(riid, IID_IShellIconOverlayIdentifier) 
        || IsEqualIID(riid, IID_IUnknown) )
    {
        *ppv = (IShellIconOverlayIdentifier*) this;
    }
    
    if (*ppv)
    {
        AddRef();
        return NOERROR;
    }

    return E_NOINTERFACE;
}
