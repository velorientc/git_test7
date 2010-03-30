
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

#ifndef DIRENTRY_H
#define DIRENTRY_H

#include <vector>

// Visual Studio has UINT32 instead of uint32_t
#ifndef uint32_t
#define uint32_t UINT32
#endif

class Winstat;

class Direntry
{
public:
    unsigned char state;
    unsigned mode;
    unsigned size;
    unsigned mtime;
    
    std::string name;

    int read(FILE* f, std::vector<char>& relpath);
    char status(const Winstat& stat) const;

    bool unset() const {
        return (state == 'n') && (mode == 0) && (size == -1) && (mtime == -1);
    }

private:
    static uint32_t ntohl(uint32_t x)
    {
        return ((x & 0x000000ffUL) << 24) |
               ((x & 0x0000ff00UL) <<  8) |
               ((x & 0x00ff0000UL) >>  8) |
               ((x & 0xff000000UL) >> 24);
    }
};

#endif

