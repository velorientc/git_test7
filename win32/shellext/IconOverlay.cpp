#include "stdafx.h"
#include "ShellExt.h"
#include "TortoiseUtils.h"
#include "StringUtils.h"
#include "QueryDirstate.h"

#include <shlwapi.h>


STDMETHODIMP CShellExt::GetOverlayInfo(
    LPWSTR pwszIconFile, int cchMax, int *pIndex, DWORD *pdwFlags)
{
    TDEBUG_TRACE("CShellExt::GetOverlayInfo: myTortoiseClass = " << myTortoiseClass);
    // icons are determined by TortoiseOverlays shim
    *pIndex = 0;
    *pdwFlags = 0;
    *pwszIconFile = 0;
    return S_OK;
}


STDMETHODIMP CShellExt::GetPriority(int *pPriority)
{
    *pPriority = 1;
    return S_OK;
}


STDMETHODIMP CShellExt::IsMemberOf(LPCWSTR pwszPath, DWORD /* dwAttrib */)
{
    ThgCriticalSection cs(GetCriticalSection());

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
    if (!HgQueryDirstate(path, filterStatus, status))
        return S_FALSE;

    if (status == myTortoiseClass)
        return S_OK;

    return S_FALSE;
}
