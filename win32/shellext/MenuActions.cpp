#include "stdafx.h"
#include "ShellExt.h"
#include "TortoiseUtils.h"
#include "StringUtils.h"

#include <stdio.h>
#include <vector>

void CShellExt::DoHgProc(const std::string &cmd, bool nofiles, bool nogui)
{
    std::string dir = GetTHgProgRoot();
    TDEBUG_TRACE("DoHgProc: THG root = " << dir);
    if (dir.empty())
    {
        TDEBUG_TRACE("DoHgProc: THG root is empty");
        return;
    }
    std::string hgcmd = Quote(dir + "\\hgproc.bat") + " --command " + cmd;
    
    if (nogui)
        hgcmd += " --nogui";
    
    std::string cwd;
    std::vector<std::string> filelist;
    if (!myFolder.empty())
    {
        cwd = myFolder;
        filelist.push_back(GetHgRepoRoot(myFolder));
    }
    else if (!myFiles.empty())
    {
        cwd = IsDirectory(myFiles[0])? myFiles[0] : DirName(myFiles[0]);
        filelist = myFiles;
    }
    else
    {
        TDEBUG_TRACE("DoHgProc: can't get cwd");
        return;
    }

    hgcmd += " --cwd " + Quote(cwd);
    hgcmd += " --root " + Quote(GetHgRepoRoot(cwd));

    if (!nofiles)
    {
        std::string tempfile = GetTemporaryFile();
        SECURITY_ATTRIBUTES sa;
        memset(&sa, 0, sizeof(sa));
        sa.nLength = sizeof(sa);
        sa.bInheritHandle = TRUE;

        TDEBUG_TRACE("DoHgProc: temp file = " << tempfile);
        HANDLE tempfileHandle = CreateFileA(tempfile.c_str(), GENERIC_WRITE,
                FILE_SHARE_READ, &sa, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, 0);
                
        for (int i=0; i<filelist.size(); i++)
        {
            DWORD dwWritten;
            TDEBUG_TRACE("DoHgProc: temp file adding " <<  filelist[i]);
            WriteFile(tempfileHandle, filelist[i].c_str(), 
                    static_cast<DWORD>(filelist[i].size()), &dwWritten, 0);
        }
        CloseHandle(tempfileHandle);
        hgcmd += " --listfile " + Quote(tempfile);
        hgcmd += " --deletelistfile" ;
    }

    LaunchCommand(hgcmd);
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
    DoHgProc("config", true);
    return NOERROR;
}

STDMETHODIMP 
CShellExt::CM_Repoconf(HWND hParent, LPCSTR pszWorkingDir, LPCSTR pszCmd,
		LPCSTR pszParam, int iShowCmd)
{
    DoHgProc("config");
    return NOERROR;
}
