// terminates the overlay icon server

#include "stdafx.h"

#include "Thgstatus.h"

extern "C" UINT __stdcall TerminateIconServer()
{
    if (Thgstatus::terminate() == 0)
    {
        // pipe ok, so icon server is running
        // -> wait a bit for icon server to shut down
        ::Sleep(5000 /* ms */);
    }
    return ERROR_SUCCESS;
}
