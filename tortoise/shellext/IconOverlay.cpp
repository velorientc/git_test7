#include "stdafx.h"
#include "ShellExt.h"
#include "TortoiseUtils.h"
#include "StringUtils.h"
#include "PipeUtils.h"
#include "dirstate.h"

#include <shlwapi.h>


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


STDMETHODIMP CShellExt::IsMemberOf(LPCWSTR pwszPath, DWORD /* dwAttrib */)
{
    std::string path = WideToMultibyte(pwszPath);

    std::string hgroot = GetHgRepoRoot(path);

    if (hgroot.empty())
        return S_FALSE;

    size_t offset = hgroot.length();
    if (path[offset] == '\\')
        offset++;
    const char* relpathptr = path.c_str() + offset;

    std::string relpath = relpathptr;

    if (relpath.empty())
        return S_FALSE; // don't show icon on repo root dir

    if (relpath.compare(0, 3, ".hg") == 0)
        return S_FALSE; // don't descend into .hg dir

    char status = 0;

    if (PathIsDirectory(path.c_str()))
    {
        if (!HgQueryDirstateDirectory(hgroot, path, relpath, status))
            return S_FALSE;
    }
    else 
    {
        if (!HgQueryDirstateFile(hgroot, path, relpath, status))
            return S_FALSE;
    }

    if (myTortoiseClass == TORTOISE_OLE_ADDED && status == 'A')
        return S_OK;
    else if (myTortoiseClass == TORTOISE_OLE_MODIFIED && status == 'M')
        return S_OK;
    else if (myTortoiseClass == TORTOISE_OLE_UNCHANGED && status == 'C')
        return S_OK;

    return S_FALSE;
}
