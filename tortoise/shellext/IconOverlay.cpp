#include "stdafx.h"
#include "ShellExt.h"
#include "TortoiseUtils.h"
#include "StringUtils.h"
#include "PipeUtils.h"

STDMETHODIMP CShellExt::GetOverlayInfo(LPWSTR pwszIconFile, int cchMax,
        int *pIndex, DWORD *pdwFlags)
{
    *pIndex = 0;
    *pdwFlags = ISIOI_ICONFILE;

    // get installation path
    std::string dir = GetTHgProgRoot();
    if (dir.empty())
    {
        TDEBUG_TRACE("GetOverlayInfo: THG root is empty");
        wcsncpy(pwszIconFile, L"", cchMax);
        return S_OK;
    }
    
    // find icon per overlay type
    std::wstring dirWide = MultibyteToWide(dir);
    wcsncpy(pwszIconFile, dirWide.c_str(), cchMax);
    cchMax -= static_cast<int>(dirWide.size()) + 1;    
/*
    switch (myTortoiseClass)
    {
        case TORTOISE_OLE_ADDED:
            wcsncat(pwszIconFile, L"\\icons\\status\\added.ico", cchMax);
            break;
        case TORTOISE_OLE_MODIFIED:
            wcsncat(pwszIconFile, L"\\icons\\status\\changed.ico", cchMax);
            break;
        case TORTOISE_OLE_UNCHANGED:
            wcsncat(pwszIconFile, L"\\icons\\status\\unchanged.ico", cchMax);
            break;
        default:
            break;
    }
*/    
    std::string path = WideToMultibyte(pwszIconFile);
    TDEBUG_TRACE("GetOverlayInfo: icon path = " << path);
    
    return S_OK;
}

STDMETHODIMP CShellExt::GetPriority(int *pPriority)
{
    *pPriority = 1;
    return S_OK;
}

#define BUFSIZE 512

STDMETHODIMP CShellExt::IsMemberOf(LPCWSTR pwszPath, DWORD /* dwAttrib */)
{
    TCHAR status[BUFSIZE] = TEXT("");
    int bufsize = BUFSIZE * sizeof(TCHAR);    
    std::string mbstr = WideToMultibyte(pwszPath);

    TDEBUG_TRACE("IsMemberOf: search for " << mbstr.c_str());
    int cbRead = query_pipe(mbstr.c_str(), status, bufsize);

    if (cbRead < 0)
        return S_FALSE;
    else if (myTortoiseClass == TORTOISE_OLE_ADDED &&
            strcmp(status, "added") == 0)
        return S_OK;
    else if (myTortoiseClass == TORTOISE_OLE_MODIFIED &&
            strcmp(status, "modified") == 0)
        return S_OK;
    else if (myTortoiseClass == TORTOISE_OLE_UNCHANGED &&
            strcmp(status, "unchanged") == 0)
        return S_OK;
       
    return S_FALSE;
}
