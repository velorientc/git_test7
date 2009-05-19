
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


std::list<Dirstatecache::E>& Dirstatecache::cache()
{
    static std::list<Dirstatecache::E> c;
    return c;
}


Dirstate* Dirstatecache::get(const std::string& hgroot)
{
    typedef std::list<E>::iterator Iter;

    Iter iter = cache().begin();
    for (;iter != cache().end(); ++iter)
    {
        if (hgroot == iter->hgroot)
            break;
    }

    Winstat stat;
    std::string path = hgroot + "\\.hg\\dirstate";

    unsigned tc = GetTickCount();
    bool new_stat = false;

    if (iter == cache().end())
    {
        if (stat.lstat(path.c_str()) != 0)
        {
            TDEBUG_TRACE("Dirstatecache::get: lstat(" << path <<") failed");
            return 0;
        }
        TDEBUG_TRACE("Dirstatecache::get: lstat(" << path <<") ok ");
        new_stat = true;

        if (cache().size() >= 10)
        {
            TDEBUG_TRACE("Dirstatecache::get: dropping "
                                            << cache().back().hgroot);
            delete cache().back().dstate;
            cache().back().dstate = 0;
            cache().pop_back();
        }

        E e;
        e.hgroot = hgroot;
        cache().push_front(e);
        iter = cache().begin();
        iter->tickcount = tc;
    }

    if (!new_stat && tc - iter->tickcount > 500)
    {
        if (0 != stat.lstat(path.c_str()))
        {
            TDEBUG_TRACE("Dirstatecache::get: lstat(" << path <<") failed");
            TDEBUG_TRACE("Dirstatecache::get: dropping " << iter->hgroot);
            delete iter->dstate;
            iter->dstate = 0;
            cache().erase(iter);
            return 0;
        }
        iter->tickcount = tc;
        TDEBUG_TRACE("Dirstatecache::get: lstat(" << path <<") ok ");
        new_stat = true;
    }

    if (iter->dstate) 
    {
        if (!new_stat)
            return iter->dstate;

        if (iter->dstate_mtime == stat.mtime
            && iter->dstate_size == stat.size)
        {
            return iter->dstate;
        }

        TDEBUG_TRACE("Dirstatecache::get: refreshing " << hgroot);
        delete iter->dstate;
        iter->dstate = 0;
    } 
    else 
    {
        TDEBUG_TRACE("Dirstatecache::get: reading " << hgroot);
    }

    unsigned tc0 = GetTickCount();
    iter->dstate = Dirstate::read(path).release();
    unsigned tc1 = GetTickCount();
    unsigned delta = tc1 - tc0;
    TDEBUG_TRACE("Dirstatecache::get: read done in " << delta << " ticks, "
        << cache().size() << " repos in cache");

    iter->dstate_mtime = stat.mtime;
    iter->dstate_size = stat.size;

    return iter->dstate;
}
