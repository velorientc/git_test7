// terminates the overlay icon server

#include "stdafx.h"

#include "Thgstatus.h"

int main(int argc, char *argv[])
{
    if (Thgstatus::terminate() == 0)
    {
        // pipe ok, so icon server is running
        // -> wait a bit for icon server to shut down
        ::Sleep(5000 /* ms */);
    }
    return 0;
}
