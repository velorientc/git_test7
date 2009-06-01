
// Copyright (C) 2009 Adrian Buehlmann
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 2 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.

#include "stdafx.h"

#include "Thgstatus.h"

#include <vector>


std::string GetPipeName()
{
    DWORD size = 260;
    std::vector<char> buf(size);
    if (!::GetUserNameA(&buf[0], &size))
        return "";
    std::string res = "\\\\.\\pipe\\TortoiseHgRpcServer-bc0c27107423-";
    res += &buf[0];
    return res;
}


int Thgstatus::update(const std::string& path)
{
    static std::string pname = GetPipeName();
    
    if (pname.empty())
        return 0;

    BOOL fSuccess;
    DWORD cbRead;

    TDEBUG_TRACE("Thgstatus::update(" << path  << ") for " << pname);

    fSuccess = ::CallNamedPipeA(
        pname.c_str(), (void*)path.c_str(), path.size(), 0, 0, &cbRead,
        200 /* ms */
    );

    DWORD err = GetLastError();
    if (fSuccess || err == ERROR_MORE_DATA || err == ERROR_PIPE_NOT_CONNECTED)
    {
        return 0;
    }
    else if (err == ERROR_PIPE_BUSY)
    {
        TDEBUG_TRACE("Thgstatus::update: CallNamedPipeA failed. " 
            "ERROR_PIPE_BUSY");
        return -1;
    }
    else
    {
        TDEBUG_TRACE("Thgstatus::update: CallNamedPipeA failed (" 
            << err << ")");
        return -1;
    }
}
