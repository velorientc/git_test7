
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

#include "Dirstatecache.h"
#include "dirstate.h"
#include "Winstat.h"

#include <list>


Dirstate* Dirstatecache::get(const std::string& hgroot)
{
    typedef std::list<E>::iterator Iter;

    static std::list<Dirstatecache::E> _cache;

    Iter iter = _cache.begin();

    for (;iter != _cache.end(); ++iter)
    {
        if (hgroot == iter->hgroot)
            break;
    }

    bool isnew = false;

    if (iter == _cache.end())
    {
        if (_cache.size() >= 10)
        {
            TDEBUG_TRACE("Dirstatecache::get: dropping " << _cache.back().hgroot);
            delete _cache.back().dstate;
            _cache.back().dstate = 0;
            _cache.pop_back();
        }
        E e;
        e.hgroot = hgroot;
        _cache.push_front(e);
        iter = _cache.begin();
        isnew = true;
    }

    unsigned tc = GetTickCount();

    std::string path = hgroot + "\\.hg\\dirstate";

    Winstat stat;

    bool stat_done = false;

    if (isnew || (tc - iter->tickcount) > 500)
    {
        if (0 != stat.lstat(path.c_str()))
        {
            TDEBUG_TRACE("Dirstatecache::get: lstat(" << path <<") failed");
            return 0;
        }
        iter->tickcount = tc;
        stat_done = true;
        TDEBUG_TRACE("Dirstatecache::get: lstat(" << path <<") ok ");
    }

    if (stat_done && iter->dstate_mtime < stat.mtime)
    {
        iter->dstate_mtime = stat.mtime;
        if (iter->dstate) {
            delete iter->dstate;
            iter->dstate = 0;
            TDEBUG_TRACE("Dirstatecache::get: refreshing " << hgroot);
        } else {
            TDEBUG_TRACE("Dirstatecache::get: reading " << hgroot);
        }
        unsigned tc0 = GetTickCount();
        iter->dstate = Dirstate::read(path).release();
        unsigned tc1 = GetTickCount();
        unsigned delta = tc1 - tc0;
        TDEBUG_TRACE("Dirstatecache::get: read done in " << delta << " ticks, "
            << _cache.size() << " repos in cache");
    }

    return iter->dstate;
}
