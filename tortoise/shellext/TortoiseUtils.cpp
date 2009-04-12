#include "stdafx.h"
#include "ShellExt.h"
#include "TortoiseUtils.h"
#include "errno.h"
#include <assert.h>

int WideCharToLocal(LPTSTR pLocal, LPWSTR pWide, DWORD dwChars)
{
	*pLocal = 0;

	#ifdef UNICODE
	lstrcpyn(pLocal, pWide, dwChars);
	#else
	WideCharToMultiByte( CP_ACP, 
						 0, 
						 pWide, 
						 -1, 
						 pLocal, 
						 dwChars, 
						 NULL, 
						 NULL);
	#endif

	return lstrlen(pLocal);
}

int LocalToWideChar(LPWSTR pWide, LPTSTR pLocal, DWORD dwChars)
{
	*pWide = 0;

	#ifdef UNICODE
	lstrcpyn(pWide, pLocal, dwChars);
	#else
	MultiByteToWideChar( CP_ACP, 
						 0, 
						 pLocal, 
						 -1, 
						 pWide, 
						 dwChars); 
	#endif

	return lstrlenW(pWide);
}

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

    RegQueryValue(key, regname, lpszValue, &lpcbLonger);
    std::string result(reinterpret_cast<char*>(lpszValue));
    return result;
}


std::string GetTHgProgRoot()
{
    LPCSTR regname = "Software\\TortoiseHg";
    HKEY key = HKEY_LOCAL_MACHINE;
    TCHAR lpszValue[MAX_PATH] = "";
    LONG lpcbLonger = MAX_PATH * sizeof(TCHAR);

    RegQueryValue(key, regname, lpszValue, &lpcbLonger);
    std::string result(reinterpret_cast<char*>(lpszValue));
    return result;
}

// Start an external command
// Note: if the command is a batch file and the [full] path to the
//       batch contains spaces, the path must be double-quoted.
//      (see http://www.encocoservices.com/createprocess.html)
bool LaunchCommand(const std::string& command, bool minimized)
{
   TDEBUG_TRACE("LaunchCommand: " << command);
   PROCESS_INFORMATION processInfo;
   STARTUPINFOA startupInfo;
   memset(&startupInfo, 0, sizeof(startupInfo));
   startupInfo.cb = sizeof(startupInfo);
   startupInfo.dwFlags = minimized ? STARTF_USESHOWWINDOW : 0;
   startupInfo.wShowWindow = SW_SHOWMINIMIZED;
   int res = CreateProcessA(0,
                            const_cast<char*>(command.c_str()),
                            0, 0,
                            FALSE,
                            CREATE_NO_WINDOW,
                            0, 0, &startupInfo, &processInfo);
   TDEBUG_TRACE("LaunchCommand: res = " << res);
   if (res == 0)
   {
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
        return std::string(tempFile);
    }
    else
    {
        TDEBUG_TRACE("GetTemporaryFile: Failed to get temporary file");
    }
    
    return std::string();
}


bool IsDirectory(const std::string& filename)
{
   DWORD attributes = GetFileAttributesA(filename.c_str());
   if (attributes == INVALID_FILE_ATTRIBUTES)
      return false;

   return (attributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
}

std::string DirName(const std::string& filename)
{
    if (filename.empty())
        return filename;
    std::string::size_type pos = filename.find_last_of("\\");
    std::string myfilename = filename.substr(0, pos);
    return myfilename;
}

std::string BaseName(const std::string& filename)
{
    if (filename.empty())
        return filename;
    std::string::size_type pos = filename.find_last_of("\\");
    std::string myfilename = filename.substr(pos+1);
    return myfilename;
}

HICON GetTortoiseIcon(const std::string& iconname)
{
    std::string thgdir = GetTHgProgRoot();
    if (thgdir.empty())
    {
        TDEBUG_TRACE("GetTortoiseIcon: THG root is empty");
        return NULL;
    }

    std::string iconpath = thgdir + "\\icons\\tortoise\\" + iconname;
    TDEBUG_TRACE("    GetTortoiseIcon: loading " + iconpath);
    HICON h = (HICON) LoadImageA(0, iconpath.c_str(), IMAGE_ICON,
            16, 16, LR_LOADFROMFILE);
    if (!h)
    {
        TDEBUG_TRACE("    GetTortoiseIcon: can't find " + iconpath);            
    }
    
    return h;
}

std::string GetHgRepoRoot(const std::string& path)
{
    TDEBUG_TRACE("    GetHgRepoRoot: find repo root for " << path);            
    std::string p = IsDirectory(path)? path : DirName(path);
    while (!IsDirectory(p + "\\.hg"))
    {
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
