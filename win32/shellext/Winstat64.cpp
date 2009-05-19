
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

#include "Winstat64.h"

int Winstat64::lstat(const char* path)
{
    WIN32_FIND_DATAA data;
    HANDLE hfind;

    hfind = FindFirstFileA(path, &data);
    if (hfind == INVALID_HANDLE_VALUE)
        return -1;
    FindClose(hfind);

    this->mtime = *(__time64_t*)&data.ftLastWriteTime;
    this->size = ((__int64)data.nFileSizeHigh << sizeof(data.nFileSizeHigh)) 
                    | data.nFileSizeLow;

    return 0;
}
