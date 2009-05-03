
// Copyright (C) 2009 Benjamin Pollack
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

#include "Direntry.h"


int lstat(const char* file, thg_stat& rstat)
{
    const __int64 days_between_epochs = 134774L; /* days between 1.1.1601 and 1.1.1970 */
    const __int64 secs_between_epochs = (__int64)days_between_epochs * 86400L;
    const __int64 divisor = 10000000L;

    WIN32_FIND_DATAA data;
    HANDLE hfind;

    hfind = FindFirstFileA(file, &data);
    if (hfind == INVALID_HANDLE_VALUE)
        return -1;
    FindClose(hfind);

    rstat.mtime = *(__int64*)&data.ftLastWriteTime / divisor - secs_between_epochs;
    rstat.size = (data.nFileSizeHigh << sizeof(data.nFileSizeHigh)) | data.nFileSizeLow;
    rstat.isdir = (data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0;

    return 0;
}


char Direntry::status(const thg_stat& stat) const
{
    switch (this->state)
    {
    case 'n':
        if (this->mtime == (unsigned)stat.mtime
            && this->size == (unsigned)stat.size
            )
            return 'C';
        else
            return 'M';
    case 'm':
        return 'M';
    case 'r':
        return 'R';
    case 'a':
        return 'A';
    default:
        return '?';
    }
}

