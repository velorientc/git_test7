#include "stdafx.h"
#include "TortoiseUtils.h"

#include <vector>
#include <assert.h>
#include <map>

#include <io.h>
#include "FCNTL.H"

#include "shlwapi.h"
#include "IconBitmapUtils.h"


LPWSTR hf_mbtowc(LPWSTR lpw, LPCSTR lpa, int nChars)
{
    assert(lpa != NULL);
    assert(lpw != NULL);

    lpw[0] = '\0';
    MultiByteToWideChar(CP_ACP, 0, lpa, -1, lpw, nChars);
    return lpw;
}


LPSTR hf_wctomb(LPSTR lpa, LPCWSTR lpw, int nChars)
{
    assert(lpw != NULL);
    assert(lpa != NULL);

    lpa[0] = '\0';
    WideCharToMultiByte(CP_ACP, 0, lpw, -1, lpa, nChars, NULL, NULL);
    return lpa;
}


std::string GetTHgShellRoot()
{
    LPCSTR regname = "Software\\TortoiseHgShell";
    HKEY key = HKEY_LOCAL_MACHINE;
    TCHAR lpszValue[MAX_PATH] = "";
    LONG lpcbLonger = MAX_PATH * sizeof(TCHAR);

    if (RegQueryValue(key, regname, lpszValue, &lpcbLonger) != ERROR_SUCCESS)
        return "";

    return lpszValue;
}


std::string GetTHgProgRoot()
{
    LPCSTR regname = "Software\\TortoiseHg";
    HKEY key = HKEY_LOCAL_MACHINE;
    TCHAR lpszValue[MAX_PATH] = "";
    LONG lpcbLonger = MAX_PATH * sizeof(TCHAR);

    if (RegQueryValue(key, regname, lpszValue, &lpcbLonger) != ERROR_SUCCESS)
        return "";

    return lpszValue;
}


int GetRegistryConfig(const std::string& name, std::string& res)
{
    const char* const subkey = "Software\\TortoiseHg";

    HKEY hkey = 0;
    LONG rv = RegOpenKeyExA(
        HKEY_CURRENT_USER, subkey, 0, KEY_READ, &hkey);

    if (rv != ERROR_SUCCESS || hkey == 0)
        return 0;

    BYTE Data[MAX_PATH] = "";
    DWORD cbData = MAX_PATH * sizeof(BYTE);

    rv = RegQueryValueExA(
        hkey, name.c_str(), 0, 0, Data, &cbData);

    int ret = 0;
    if (rv == ERROR_SUCCESS)
    {
        res = reinterpret_cast<const char*>(&Data);
        ret = 1;
    }

    RegCloseKey(hkey);
    return ret;
}


// Start an external command
// Note: if the command is a batch file and the [full] path to the
//       batch contains spaces, the path must be double-quoted.
//      (see http://www.encocoservices.com/createprocess.html)
bool LaunchCommand(const std::string& command, const std::string& cwd)
{
    TDEBUG_TRACE("LaunchCommand: " << command);
    TDEBUG_TRACE("LaunchCommand: in " << cwd);
    PROCESS_INFORMATION processInfo;
    memset(&processInfo, 0, sizeof(processInfo));

    STARTUPINFOA startupInfo;
    memset(&startupInfo, 0, sizeof(startupInfo));

    int res = CreateProcessA(
        NULL,  // No module name, use command line
        const_cast<char*>(command.c_str()),
        NULL,  // Process handle not inherited
        NULL,  // Thread handle not inherited
        FALSE,
        CREATE_NO_WINDOW,
        NULL,  // use parent's environment
        const_cast<char*>(cwd.c_str()),
        &startupInfo,
        &processInfo
    );

    if (res == 0)
    {
        TDEBUG_TRACE("LaunchCommand: failed to launch");
        return false;
    }

    CloseHandle(processInfo.hProcess);
    CloseHandle(processInfo.hThread);
    return true;
}

std::string GetTemporaryFile(LPCTSTR prefix)
{
    char tempDir[MAX_PATH + 1];
    char tempFile[MAX_PATH + 1];
    
    if (GetTempPath(MAX_PATH, tempDir) == 0)
    {
        TDEBUG_TRACE("GetTemporaryFile: Failed to find temporary path");
    }
    else if (GetTempFileName(tempDir, prefix, 0, tempFile) != 0)
    {
        return tempFile;
    }
    else
    {
        TDEBUG_TRACE("GetTemporaryFile: Failed to get temporary file");
    }
    
    return "";
}


bool IsDirectory(const std::string& filename)
{
   return ::PathIsDirectory(filename.c_str()) != 0;
}


std::string DirName(const std::string& filename)
{
    if (filename.empty())
        return filename;
    std::string::size_type pos = filename.find_last_of("\\");
    if (pos == std::string::npos)
        return "";
    std::string myfilename = filename.substr(0, pos);
    if (myfilename.size() > 0 && myfilename[myfilename.size()-1] == ':')
        myfilename.push_back('\\');
    return myfilename;
}

std::string BaseName(const std::string& filename)
{
    if (filename.empty())
        return filename;
    std::string::size_type pos = filename.find_last_of("\\");
    if (pos == std::string::npos)
        return filename;
    return filename.substr(pos+1);
}


// not reentrant
HICON GetTortoiseIcon(const std::string& iconname)
{
    typedef std::map<std::string, HICON> IconCacheT;
    static IconCacheT iconcache_;

    std::string thgdir = GetTHgProgRoot();
    if (thgdir.empty())
    {
        TDEBUG_TRACE("GetTortoiseIcon: THG root is empty");
        return 0;
    }

    const std::string iconpath = thgdir + "\\icons\\" + iconname;

    IconCacheT::const_iterator i = iconcache_.find(iconpath);
    if (i != iconcache_.end())
        return i->second;

    if (iconcache_.size() > 200)
    {
        TDEBUG_TRACE("**** GetTortoiseIcon: error: too many icons in cache");
        return 0;
    }

    HICON h = (HICON) LoadImageA(0, iconpath.c_str(), IMAGE_ICON,
            16, 16, LR_LOADFROMFILE);
    if (!h)
    {
        TDEBUG_TRACE("GetTortoiseIcon: can't find " + iconpath);
        return 0;
    }

    iconcache_[iconpath] = h;

    TDEBUG_TRACE(
        "GetTortoiseIcon: added '" << iconpath << "' to iconcache_"
        " (" << iconcache_.size() << " icons in cache)"
    );

    return h;
}

HBITMAP GetTortoiseIconBitmap(const std::string& iconname)
{
    IconBitmapUtils bmpUtils;
    typedef std::map<std::string, HBITMAP> BitmapCacheT;
    static BitmapCacheT bmpcache_;

   BitmapCacheT::const_iterator i = bmpcache_.find(iconname);
    if (i != bmpcache_.end())
        return i->second;

    if (bmpcache_.size() > 200)
    {
        TDEBUG_TRACE("**** GetTortoiseIconBitmap: error: too many bitmaps in cache");
        return 0;
    }

    HICON hIcon = GetTortoiseIcon(iconname);
    if (!hIcon)
        return 0;

    HBITMAP hBmp = bmpUtils.IconToBitmapPARGB32(hIcon);
    if (!hBmp)
    {
        TDEBUG_TRACE("**** GetTortoiseIconBitmap: error: something wrong in bmpUtils.ConvertToPARGB32(hIcon)");
        return 0;
    }

    bmpcache_[iconname] = hBmp;

    TDEBUG_TRACE(
        "GetTortoiseIconBitmap: added '" << iconname << "' to bmpcache_"
        " (" << bmpcache_.size() << " bitmaps in cache)"
    );

    return hBmp;
}


std::string GetHgRepoRoot(const std::string& path)
{
    std::string p = IsDirectory(path)? path : DirName(path);
    for (;;)
    {
        std::string tdir = p + "\\.hg";
        if (IsDirectory(tdir))
            break;
        std::string oldp = p;
        p = DirName(p);
        if (p == oldp)
        {
            p.clear();
            break;
        }
    }
    return p;
}


bool IsHgRepo(const std::string& path)
{
    return !GetHgRepoRoot(path).empty();
}


// open a file for reading, allowing renames and deletes by other
// processes while we have it open
FILE* fopenReadRenameAllowed(const char* path)
{
    HANDLE fh = ::CreateFileA(
      path, GENERIC_READ,
      FILE_SHARE_DELETE | FILE_SHARE_READ | FILE_SHARE_WRITE,
      0, OPEN_EXISTING, 0, 0
    );

    if (fh == INVALID_HANDLE_VALUE)
        return 0;

    // get C runtime file descriptor from file handle
    int fd = ::_open_osfhandle((intptr_t)fh, _O_RDONLY);
    if (fd == -1)
    {
        TDEBUG_TRACE("fopenReadRenameAllowed: _open_osfhandle failed");
        ::CloseHandle(fh);
        return 0;
    }

    // get C runtime FILE from file descriptor
    FILE* f = ::_fdopen(fd, "r");
    if (f == 0)
    {
        TDEBUG_TRACE("fopenReadRenameAllowed: _fdopen failed");
        ::_close(fd);
        return 0;
    }

    return f;
}


// read string value from registry
int GetRegSZValue(HKEY hkey, const char* name, std::string& res)
{
    res = "";

    if (!hkey)
        return 0;

    std::vector<BYTE> Data(300);
    DWORD cbData = Data.size();

    LONG rv = ::RegQueryValueExA(hkey, name, 0, 0, &Data[0], &cbData);

    if (rv == ERROR_SUCCESS)
    {
        res = reinterpret_cast<char*>(&Data[0]);
        return 1;
    }

    TDEBUG_TRACE("GetRegSZValue(" << name << ") failed");

    return 0;
}

// read string value from registry, wide version
int GetRegSZValueW(HKEY hkey, const wchar_t* name, std::wstring& res)
{
    res = L"";

    if (!hkey)
        return 0;

    std::vector<BYTE> Data(600);
    DWORD cbData = Data.size();

    LONG rv = ::RegQueryValueExW(hkey, name, 0, 0, &Data[0], &cbData);

    if (rv == ERROR_SUCCESS)
    {
        res = reinterpret_cast<wchar_t*>(&Data[0]);
        return 1;
    }

    TDEBUG_TRACEW(L"GetRegSZValueW(\"" << name << L"\") failed");

    return 0;
}


// true if a starts with b
bool StartsWith(const std::string& a, const std::string& b)
{
    if (a.empty() || b.empty())
        return false;

    if (b.size() > a.size())
        return false;

    for (std::string::size_type i = 0; i < b.size(); ++i)
    {
        if (a[i] != b[i])
            return false;
    }

    return true;
}

