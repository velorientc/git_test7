#include "stdafx.h"
#include "ShellExt.h"
#include "TortoiseUtils.h"
#include "StringUtils.h"

#include <stdio.h>
#include <vector>

void CShellExt::DoHgProc(const std::string &cmd)
{
    std::string dir = GetTHgProgRoot();
    TDEBUG_TRACE("DoHgProc: THG root = " << dir);
    if (dir.empty())
    {
        TDEBUG_TRACE("DoHgProc: THG root is empty");
        return;
    }
    std::string hgcmd = Quote(dir + "\\hgtk.exe") + " " + cmd;
    
    std::string cwd;
    if (!myFolder.empty())
    {
        cwd = myFolder;
    }
    else if (!myFiles.empty())
    {
        cwd = IsDirectory(myFiles[0])? myFiles[0] : DirName(myFiles[0]);

        std::string tempfile = GetTemporaryFile();
        SECURITY_ATTRIBUTES sa;
        memset(&sa, 0, sizeof(sa));
        sa.nLength = sizeof(sa);
        sa.bInheritHandle = TRUE;

        TDEBUG_TRACE("DoHgProc: temp file = " << tempfile);
        HANDLE tempfileHandle = CreateFileA(tempfile.c_str(), GENERIC_WRITE,
                FILE_SHARE_READ, &sa, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, 0);
                
        for (int i=0; i<myFiles.size(); i++)
        {
            DWORD dwWritten;
            TDEBUG_TRACE("DoHgProc: temp file adding " <<  myFiles[i]);
            WriteFile(tempfileHandle, myFiles[i].c_str(), 
                    static_cast<DWORD>(myFiles[i].size()), &dwWritten, 0);
            WriteFile(tempfileHandle, "\n", 1, &dwWritten, 0);
        }
        CloseHandle(tempfileHandle);
        hgcmd += " --listfile " + Quote(tempfile);
    }
    else
    {
        TDEBUG_TRACE("DoHgProc: can't get cwd");
        return;
    }

    LaunchCommand(hgcmd, cwd);
}

STDMETHODIMP 
CShellExt::CM_Commit(HWND hParent, LPCSTR pszWorkingDir, LPCSTR pszCmd,
		LPCSTR pszParam, int iShowCmd)
{
    DoHgProc("commit");
    return NOERROR;
}

STDMETHODIMP 
CShellExt::CM_Status(HWND hParent, LPCSTR pszWorkingDir, LPCSTR pszCmd,
		LPCSTR pszParam, int iShowCmd)
{
    DoHgProc("status");
    return NOERROR;
}

STDMETHODIMP 
CShellExt::CM_Log(HWND hParent, LPCSTR pszWorkingDir, LPCSTR pszCmd,
		LPCSTR pszParam, int iShowCmd)
{
    DoHgProc("log");
    return NOERROR;
}

STDMETHODIMP 
CShellExt::CM_About(HWND hParent, LPCSTR pszWorkingDir, LPCSTR pszCmd,
		LPCSTR pszParam, int iShowCmd)
{
    DoHgProc("about");
    return NOERROR;
}

STDMETHODIMP 
CShellExt::CM_Synch(HWND hParent, LPCSTR pszWorkingDir, LPCSTR pszCmd,
		LPCSTR pszParam, int iShowCmd)
{
    DoHgProc("synch");
    return NOERROR;
}

STDMETHODIMP 
CShellExt::CM_Serve(HWND hParent, LPCSTR pszWorkingDir, LPCSTR pszCmd,
		LPCSTR pszParam, int iShowCmd)
{
    DoHgProc("serve");
    return NOERROR;
}

STDMETHODIMP 
CShellExt::CM_Update(HWND hParent, LPCSTR pszWorkingDir, LPCSTR pszCmd,
		LPCSTR pszParam, int iShowCmd)
{
    DoHgProc("update");
    return NOERROR;
}

STDMETHODIMP 
CShellExt::CM_Recover(HWND hParent, LPCSTR pszWorkingDir, LPCSTR pszCmd,
		LPCSTR pszParam, int iShowCmd)
{
    DoHgProc("recovery");
    return NOERROR;
}

STDMETHODIMP 
CShellExt::CM_Userconf(HWND hParent, LPCSTR pszWorkingDir, LPCSTR pszCmd,
		LPCSTR pszParam, int iShowCmd)
{
    DoHgProc("userconfig");
    return NOERROR;
}

STDMETHODIMP 
CShellExt::CM_Repoconf(HWND hParent, LPCSTR pszWorkingDir, LPCSTR pszCmd,
		LPCSTR pszParam, int iShowCmd)
{
    DoHgProc("repoconfig");
    return NOERROR;
}

STDMETHODIMP 
CShellExt::CM_thgstatus(HWND hParent, LPCSTR pszWorkingDir, LPCSTR pszCmd,
		LPCSTR pszParam, int iShowCmd)
{
    DoHgProc("thgstatus");
    return NOERROR;
}
