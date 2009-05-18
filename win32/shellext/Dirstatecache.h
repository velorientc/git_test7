
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

#ifndef _DIRSTATECACHE_H
#define _DIRSTATECACHE_H

#include <string>

class Dirstate;

class Dirstatecache
{
    struct E
    {
        Dirstate*       dstate;
        __time64_t      dstate_mtime;
        unsigned        dstate_size;

        std::string     hgroot;
        unsigned        tickcount;

        E(): dstate(0), dstate_mtime(0), dstate_size(0), tickcount(0) {}         
    };

public:
    static Dirstate* get(const std::string& hgroot);
};

#endif
