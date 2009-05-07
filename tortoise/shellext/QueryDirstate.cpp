
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

#include "QueryDirstate.h"
#include "dirstate.h"
#include "DirectoryStatus.h"
#include "TortoiseUtils.h"
#include "Winstat.h"

#include <shlwapi.h>

#include <vector>
#include <list>


#define HASH_LENGTH 20


class Dirstatecache
{
    struct E
    {
        Dirstate*       dstate;
        __time64_t      dstate_mtime;

        std::string     hgroot;
        unsigned        tickcount;

        E(): dstate(0), dstate_mtime(0), tickcount(0) {}         
    };

    typedef std::list<E>::iterator Iter;

    static std::list<E> _cache;

public:
    static Dirstate* get(const std::string& hgroot);
};

std::list<Dirstatecache::E> Dirstatecache::_cache;


Dirstate* Dirstatecache::get(const std::string& hgroot)
{
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


int HgQueryDirstate(
    const std::string& path, const char& filterStatus, char& outStatus)
{
    if (PathIsRoot(path.c_str()))
        return 0;

    std::string hgroot = GetHgRepoRoot(path);
    if (hgroot.empty())
        return 0;

    size_t offset = hgroot.length();
    if (path[offset] == '\\')
        offset++;
    const char* relpathptr = path.c_str() + offset;

    std::string relpath = relpathptr;

    for (size_t i = 0; i < relpath.size(); ++i)
    {
        if (relpath[i] == '\\')
            relpath[i] = '/';
    }

    if (relpath == ".hg" 
            || (relpath.size() > 4 && relpath.compare(0, 4, ".hg/") == 0))
        return 0; // don't descend into .hg dir

    Dirstate* pds = Dirstatecache::get(hgroot);
    if (!pds)
    {
        TDEBUG_TRACE("HgQueryDirstate: Dirstatecache::get(" 
            << hgroot << ") returns no Dirstate");
        return 0;
    }

    if (filterStatus == 'A' && pds->num_added() == 0)
        return 0;

    if (PathIsDirectory(path.c_str()))
    {
        std::auto_ptr<DirectoryStatus> pds(new DirectoryStatus());
        if (!pds->read(hgroot))
            return 0;

        outStatus = pds->status(relpath);
    }
    else
    {
        const Direntry* e = pds->root().get(relpath);
        if (!e)
            return 0;

        Winstat stat;
        if (0 != stat.lstat(path.c_str())) {
            TDEBUG_TRACE("HgQueryDirstate: lstat(" << path << ") failed");
            return 0;
        }

        outStatus = e->status(stat);
    }

    return 1;
}
