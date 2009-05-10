// TortoiseCVS - a Windows shell extension for easy version control

// Copyright (C) 2001 - Francis Irving
// <francis@flourish.org> - May 2001

// This program is free software; you can redistribute it and/or
// modify it under the terms of the GNU General Public License
// as published by the Free Software Foundation; either version 2
// of the License, or (at your option) any later version.

// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.

// You should have received a copy of the GNU General Public License
// along with this program; if not, write to the Free Software
// Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.


#include "StdAfx.h"
#include "ShellUtils.h"
#include "StringUtils.h"


// We don't use SHGetSpecialFolderPath as older versions
// of Windows NT don't support it.
std::string GetSpecialFolder(int nFolder)
{
   HRESULT hr;
   LPITEMIDLIST pidl = 0;
   std::string result;
   hr = SHGetSpecialFolderLocation(NULL, nFolder, &pidl);
   if (FAILED(hr))
      goto Cleanup;

   result = GetPathFromIDList(pidl);

Cleanup:
   if (pidl)
      ItemListFree(pidl);
   return result;
}


void ItemListFree(LPITEMIDLIST pidl)
{
    if ( pidl )
    {
        LPMALLOC pMalloc;
        SHGetMalloc(&pMalloc);
        if ( pMalloc )
        {
            pMalloc->Free(pidl);
            pMalloc->Release();
        }
        else
        {
            ASSERT(false);
        }
    }
}


// Get path from IDList
std::string GetPathFromIDList(LPCITEMIDLIST pidl)
{
    std::string result;
    static char dir[MAX_PATH + 1];
   
    if(SHGetPathFromIDListA(pidl, dir))
        result = dir;
    return result;
}


// Is PIDL a shortcut
bool IsShortcut(LPCITEMIDLIST pidl)
{
   TDEBUG_ENTER("IsShortcut");
   DWORD dwAttributes = SFGAO_LINK;
   if (ShellGetFileAttributesPidl(pidl, &dwAttributes))
   {
      if (dwAttributes & SFGAO_LINK)
      {
         TDEBUG_TRACE("return true");
         return true;
      }
   }
   TDEBUG_TRACE("return false");
   return false;
}


// Get target of a shortcut
LPITEMIDLIST GetShortcutTarget(LPCITEMIDLIST pidl)
{
   HRESULT hr;
   IShellLink *pShLink = 0;
   IPersistFile *ppf = 0;
   std::wstring wsPath;
   LPITEMIDLIST pidlResult = 0;

   // If it's not a shortcut, exit
   if (!IsShortcut(pidl))
   {
      pidlResult = CloneIDList(pidl);
      goto Cleanup;
   }

   // get path of shortcut
   wsPath = MultibyteToWide(GetPathFromIDList(pidl));

   hr = CoCreateInstance(CLSID_ShellLink, NULL, CLSCTX_INPROC_SERVER,
      IID_IShellLink, (LPVOID*) &pShLink);

   if (FAILED(hr))
      goto Cleanup;

   hr = pShLink->QueryInterface(IID_IPersistFile, (LPVOID*) &ppf);
   if (FAILED(hr))
      goto Cleanup;

   hr = ppf->Load(wsPath.c_str(), STGM_READ);
   if (FAILED(hr))
      goto Cleanup;


   hr = pShLink->Resolve(GetDesktopWindow(), SLR_NO_UI);
   if (FAILED(hr))
      goto Cleanup;

   hr = pShLink->GetIDList(&pidlResult);
   if (FAILED(hr))
      goto Cleanup;

Cleanup:
   if (pShLink)
      pShLink->Release();
   
   if (ppf)
      ppf->Release();

   return pidlResult;
}


// Returns the concatination of the two PIDLs. Neither passed PIDLs are
// freed so it is up to the caller to free them.
LPITEMIDLIST AppendPIDL(LPCITEMIDLIST dest, LPCITEMIDLIST src)
{
   LPMALLOC pMalloc;
   if (!SUCCEEDED(SHGetMalloc(&pMalloc)))
      return NULL;

   int destSize = 0;
   int srcSize = 0;

   // Appending a PIDL to the DesktopPIDL is invalid so don't allow it.
   if (dest != NULL && !IsDesktopFolder(dest))
      destSize = GetSize(dest) - sizeof(dest->mkid.cb);
      
   if (src != NULL)
      srcSize = GetSize(src);
   
   LPITEMIDLIST sum = (LPITEMIDLIST)pMalloc->Alloc(destSize + srcSize);
   if (sum != NULL)
   {
      if (dest != NULL)
         CopyMemory((char*)sum, dest, destSize);
      if (src != NULL)
         CopyMemory((char*)sum + destSize, src, srcSize);
   }
   
   pMalloc->Release();
   return sum;
}


// Get attributes for file (contains bugfix for SHGetFileInfo)
BOOL MyShellGetFileAttr(const void* data, DWORD *attr, bool bIsPidl)
{
   TDEBUG_ENTER("MyShellGetFileAttr");
#ifndef UNICODE
   // Workaround for NT4 bug: SHGetFileInfoA doesn't work correclty,
   // so use SHGetFileInfoW

   if (WindowsVersionIsNT4())
   {
      TDEBUG_TRACE("Windows NT4 workaround");
      SHFILEINFOW fi;
      std::wstring ws;
      DWORD dwFlags = SHGFI_ATTRIBUTES;
      if (attr == 0)
      {
         SetLastError(ERROR_INVALID_PARAMETER);
         return false;
      }
      if (*attr != 0)
      {
         TDEBUG_TRACE("Attributes: " << *attr);
         fi.dwAttributes = *attr;
         dwFlags |= SHGFI_ATTR_SPECIFIED;
      }
      if (bIsPidl)
      {
         TDEBUG_TRACE("It's a PIDL");
         dwFlags |= SHGFI_PIDL;
      }
      else
      {
         TDEBUG_TRACE("It's a path:" << (const char *) data);
         ws = MultibyteToWide((const char *) data, 0);
         data = ws.c_str();
      }

      DWORD dwResult = SHGetFileInfoW((LPWSTR) data, 0, &fi, sizeof(fi), 
         dwFlags);
      *attr = fi.dwAttributes;
      return (dwResult != 0);
   }
#endif

   SHFILEINFOA fi;
   DWORD dwFlags = SHGFI_ATTRIBUTES;
   if (attr != 0)
   {
      fi.dwAttributes = *attr;
      dwFlags |= SHGFI_ATTR_SPECIFIED;
   }
   if (bIsPidl)
      dwFlags |= SHGFI_PIDL;

   DWORD dwResult = SHGetFileInfoA((LPCSTR) data, 0, &fi, sizeof(fi), dwFlags);
   *attr = fi.dwAttributes;
   return (dwResult != 0);
}


// Get attributes for file (contains bugfix for SHGetFileInfo)
BOOL ShellGetFileAttributes(const char* filename, DWORD *attr)
{
   return MyShellGetFileAttr(filename, attr, false);
}


// Get attributes for file (contains bugfix for SHGetFileInfo)
BOOL ShellGetFileAttributesPidl(LPCITEMIDLIST pidl, DWORD *attr)
{
   return MyShellGetFileAttr(pidl, attr, true);
}


// Tests the passed PIDL to see if it is the root Desktop Folder
bool IsDesktopFolder(LPCITEMIDLIST pidl)
{
   if (pidl != NULL)
      return pidl->mkid.cb == 0;
   else
      return false;
}


bool IsEqualPIDL(LPCITEMIDLIST a, LPCITEMIDLIST b)
{
   UINT asiz = GetSize(a);
   UINT bsiz = GetSize(b);
   if (asiz != bsiz)
      return false;

   if (memcmp(a, b, asiz) == 0)
      return true;

   return false;
}

LPCITEMIDLIST GetNextItem(LPCITEMIDLIST pidl)
{
    if (pidl == NULL)
        return NULL;

    // Get size of the item identifier we are on
    int cb = pidl->mkid.cb;

    // If zero, then end of list
    if (cb == 0)
        return NULL;
    
    // Move on
    pidl = (LPITEMIDLIST) (((LPBYTE)pidl) + cb);

    // Return NULL if null-terminating, or pidl otherwise
    return (pidl->mkid.cb == 0) ? NULL : (LPITEMIDLIST) pidl;
}

int GetItemCount(LPCITEMIDLIST pidl)
{
    int count = 0;

    while (pidl != 0)
    {
       count++;
       pidl = GetNextItem(pidl);
    }

    return count;
}

UINT GetSize(LPCITEMIDLIST pidl)
{
    UINT total = 0;
    if (pidl)
    {
        total += sizeof(pidl->mkid.cb);
        while (pidl)
        {
            total += pidl->mkid.cb;
            pidl = GetNextItem(pidl);
        }
    }
    return total;
}

LPITEMIDLIST DuplicateItem(LPMALLOC pMalloc, LPCITEMIDLIST pidl)
{
    int cb = pidl->mkid.cb;
    if (cb == 0)
        return NULL;

    LPITEMIDLIST pidlRet = (LPITEMIDLIST)pMalloc->Alloc(cb + sizeof(USHORT));
    if (pidlRet == NULL)
        return NULL;

    CopyMemory(pidlRet, pidl, cb);
    *((USHORT*) (((LPBYTE)pidlRet) + cb)) = 0;
    return pidlRet;
}


// Clone a PIDL
LPITEMIDLIST CloneIDList(LPCITEMIDLIST pidl)
{
   LPITEMIDLIST pidlResult = 0;
   DWORD dwSize;
   LPMALLOC pMalloc;

   if (!SUCCEEDED(SHGetMalloc(&pMalloc)))
      goto Cleanup;

   dwSize = GetSize(pidl);
   if (dwSize == 0)
      goto Cleanup;

   pidlResult = (LPITEMIDLIST) pMalloc->Alloc(dwSize);
   if (!pidlResult)
      goto Cleanup;

   CopyMemory(pidlResult, pidl, dwSize);

Cleanup:
   if (pMalloc)
      pMalloc->Release();

   return pidlResult;
}

