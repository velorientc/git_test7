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
bool LaunchCommand(const std::string& command, const std::string& cwd, std::vector<std::string> filelist)
{
   TDEBUG_TRACE("LaunchCommand: " << command);
   PROCESS_INFORMATION processInfo;
   memset(&processInfo, 0, sizeof(processInfo));

   HANDLE hChildStd_IN_Rd = NULL;
   HANDLE hChildStd_IN_Wr = NULL;

   SECURITY_ATTRIBUTES saAttr; 
   // Set the bInheritHandle flag so pipe handles are inherited. 
   saAttr.nLength = sizeof(SECURITY_ATTRIBUTES); 
   saAttr.bInheritHandle = TRUE; 
   saAttr.lpSecurityDescriptor = NULL; 

   // Create a pipe for the child process's STDIN. 
   if (!CreatePipe(&hChildStd_IN_Rd, &hChildStd_IN_Wr, &saAttr, 0)) 
   {
      TDEBUG_TRACE("LaunchCommand: unable to create stdin pipe");
      return false;
   }

   // Ensure the write handle to the pipe for STDIN is not inherited. 
   if (!SetHandleInformation(hChildStd_IN_Wr, HANDLE_FLAG_INHERIT, 0) )
   {
      TDEBUG_TRACE("LaunchCommand: unable to clear stdin write handle");
      return false;
   }
 
   STARTUPINFOA startupInfo;
   memset(&startupInfo, 0, sizeof(startupInfo));
   startupInfo.cb = sizeof(startupInfo);
   startupInfo.hStdInput = hChildStd_IN_Rd;
   startupInfo.dwFlags |= STARTF_USESTDHANDLES;

   int res = CreateProcessA(NULL,  // No module name, use command line
                            const_cast<char*>(command.c_str()),
                            NULL,  // Process handle not inherited
                            NULL,  // Thread handle not inherited
                            FALSE,
                            CREATE_NO_WINDOW,
                            NULL,  // use parent's environment
                            const_cast<char*>(cwd.c_str()),
                            &startupInfo,
                            &processInfo);
   if (res == 0)
   {
      TDEBUG_TRACE("LaunchCommand: failed to launch");
      return false;
   }

   std::string writename;
   for( DWORD i = 0 ; i < filelist.size(); i++ )
   {
       bool bSuccess;
       DWORD dwWritten;

       writename = filelist[i];
       writename.push_back('\n');
               
       bSuccess = WriteFile(hChildStd_IN_Wr, writename.c_str(), writename.size(), &dwWritten, NULL);
       if ( !bSuccess )
           break; 
   }
 
   if ( !CloseHandle(hChildStd_IN_Wr) ) 
   {
      TDEBUG_TRACE("LaunchCommand: Unable to close process stdin");
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
    if (myfilename.size() > 0 && myfilename[myfilename.size()-1] == ':')
        myfilename.push_back('\\');
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

