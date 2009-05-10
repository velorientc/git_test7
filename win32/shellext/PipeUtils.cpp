#include "stdafx.h"
#include "PipeUtils.h"
#include "StringUtils.h"
#include "TortoiseUtils.h"
#include <stdio.h>
#include <conio.h>
#include <tchar.h>
#include <wchar.h>

LPTSTR lpszPipename = TEXT("\\\\.\\pipe\\PyPipeService");

#define BUFSIZE 512

int query_pipe(LPCSTR cstr, TCHAR *chReadBuf, int bufsize)
{
    BOOL fSuccess;
    DWORD cbRead;

    int outlen = (lstrlen((TCHAR*)cstr))*sizeof(TCHAR);
    TDEBUG_TRACE("sending " << outlen << " bytes to pipe: " << cstr);
    
    fSuccess = CallNamedPipe(
            lpszPipename,               // pipe name
            (void *)cstr,                  // message to server
            outlen, // message length
            chReadBuf,                  // buffer to receive reply
            bufsize,                    // size of read buffer
            &cbRead,                    // number of bytes read
            NMPWAIT_NOWAIT);            // waits for 0 seconds

    if (fSuccess || GetLastError() == ERROR_MORE_DATA)
    {
        TDEBUG_TRACE("receive " << cbRead << " bytes from pipe: " << chReadBuf);
        return cbRead;
    }
    else
    {
        return -1;
    }
}

int _test_pipe(LPCSTR lpszWrite)
{
    TCHAR readBuf[BUFSIZE] = TEXT("");
    int bufsize = BUFSIZE*sizeof(TCHAR);
    int cbRead = query_pipe(lpszWrite, readBuf, bufsize);
    
    if (cbRead >= 0)
    {
        _tprintf( TEXT("read: %s\n"), readBuf );
    }
    else
    {
        _tprintf( TEXT("error calling pipe\n") );    
    }
}

#ifdef APPMAIN
int _tmain(int argc, TCHAR *argv[])
{
    LPTSTR lpszWrite = TEXT("");

    if (argc < 2)
    {
        _tprintf(TEXT("usage: %s file1 file2 ...\n"), argv[0]);
        return 1;
    }

    for (int i=1; i<argc; i++)
    {
        lpszWrite = argv[i];
        _test_pipe(lpszWrite);
    }
    WCHAR file[] = L"C:\\hg\\hg-tortoise\\hgproc.py";
    std::string mbstr = WideToMultibyte(file);
    const char *cstr = mbstr.c_str();
    _test_pipe(cstr);

    std::string root = GetTHgProgRoot();
    if (root != "")
    {
        _tprintf(TEXT("THG root = %s\n"), root.c_str() );    
    }
    else
    {
        _tprintf(TEXT("THG root not found in registry\n"));    
    }
    
    //LaunchCommand("notepad");
    //LaunchCommand("D:\\Profiles\\r28629\\My Documents\\Mercurial\\repos\\hg-tortoise-dev\\dist\\hgproc.exe")
    //LaunchCommand("\"D:\\Profiles\\r28629\\My Documents\\Mercurial\\repos\\hg-tortoise-namedpipe\\hgproc.bat\"");

    return 0;
}
#endif
