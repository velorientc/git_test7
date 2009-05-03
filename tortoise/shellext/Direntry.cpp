
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
#include "Winstat.h"


int Direntry::read(FILE* f, std::vector<char>& relpath)
{
    if (fread(&state, sizeof(state), 1, f) != 1)
        return 0;

    unsigned length = 0;

    fread(&mode, sizeof(mode), 1, f);
    fread(&size, sizeof(size), 1, f);
    fread(&mtime, sizeof(mtime), 1, f);
    fread(&length, sizeof(length), 1, f);

    mode = ntohl(mode);
    size = ntohl(size);
    mtime = ntohl(mtime);
    length = ntohl(length);

    relpath.resize(length + 1, 0);
    fread(&relpath[0], sizeof(char), length, f);
    relpath[length] = 0;

    return 1;
}


char Direntry::status(const Winstat& stat) const
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

