
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
#include "Dirstatecache.h"
#include "HgRepoRoot.h"
#include "Winstat.h"
#include "TortoiseUtils.h"

#include <shlwapi.h>


class QueryState
{
public:
    std::string path;
    bool        isdir;
    std::string basedir;
    std::string hgroot;

    char        status;
    unsigned    tickcount;

    QueryState(): isdir(false), status(0), tickcount(0) {}
};


bool hasHgDir(std::string path)
{
    path += "\\.hg";
    return PathIsDirectory(path.c_str());
}


int findHgRoot(QueryState& cur, QueryState& last, bool outdated)
{
    if (cur.isdir)
    {
        std::string p = cur.path;
        p.push_back('\\');
        if (p.find(".hg\\") != std::string::npos) 
        {
            //TDEBUG_TRACE("findHgRoot: skipping '" << cur.path << "'");
            last = cur;
            return 0;
        }
    }

    if (cur.isdir && hasHgDir(cur.path))
    {
        cur.hgroot = cur.path;
        TDEBUG_TRACE("findHgRoot(" << cur.path << "): hgroot = cur.path");
        return 1;
    }

    cur.basedir = DirName(cur.path);

    if (!outdated && !last.basedir.empty() && cur.basedir == last.basedir)
    {
        cur.hgroot = last.hgroot;
        // TDEBUG_TRACE("findHgRoot(" << cur.path << "): hgroot = '" << cur.hgroot
        //    << "'  (same as last.basedir)");
        return 1;
    }

    for (std::string p = cur.basedir;;)
    {
        if (hasHgDir(p)) {
            cur.hgroot = p;
            TDEBUG_TRACE("findHgRoot(" << cur.path << "): hgroot = '" << cur.hgroot
                << "' (found repo)");
            return 1;
        }
        std::string p2 = DirName(p);
        if (p2.size() == p.size())
            break;
        p.swap(p2);
    }

    TDEBUG_TRACE("findHgRoot(" << cur.path << "): NO repo found");
    last = cur;
    return 0;
}


int HgQueryDirstate(
    const std::string& path, const char& filterStatus, char& outStatus)
{
    static QueryState last;

    if (path.empty())
        return 0;

    QueryState cur;

    cur.path = path;
    cur.tickcount = GetTickCount();

    const bool outdated = cur.tickcount - last.tickcount > 2000;

    if (!outdated && last.path == path) 
    {
        outStatus = last.status;
        return 1;
    }

    if (PathIsRoot(path.c_str()))
    {
        last = cur;
        return 0;
    }

    cur.isdir = PathIsDirectory(cur.path.c_str());

    if (findHgRoot(cur, last, outdated) == 0)
        return 0;

    size_t offset = cur.hgroot.length();

    if (offset == 0)
    {
        last = cur;
        return 0;
    }

    if (path[offset] == '\\')
        offset++;
    const char* relpathptr = path.c_str() + offset;

    std::string relpath = relpathptr;

    for (size_t i = 0; i < relpath.size(); ++i)
    {
        if (relpath[i] == '\\')
            relpath[i] = '/';
    }

    if (cur.isdir)
    {
        DirectoryStatus* pds = DirectoryStatus::get(cur.hgroot);
        if (!pds) {
            last = cur;
            return 0;
        }

        outStatus = pds->status(relpath);
    }
    else
    {
        Dirstate* pds = Dirstatecache::get(cur.hgroot);
        if (!pds)
        {
            TDEBUG_TRACE("HgQueryDirstate: Dirstatecache::get(" 
                << cur.hgroot << ") returns no Dirstate");
            last = cur;
            return 0;
        }

        if (filterStatus == 'A' && pds->num_added() == 0) {
            last = cur;
            return 0;
        }

        const Direntry* e = pds->root().get(relpath);
        if (!e) {
            last = cur;
            return 0;
        }

        Winstat stat;
        if (0 != stat.lstat(path.c_str())) {
            TDEBUG_TRACE("HgQueryDirstate: lstat(" << path << ") failed");
            last = cur;
            return 0;
        }

        outStatus = e->status(stat);
    }

    cur.status = outStatus;
    cur.tickcount = GetTickCount();
    last = cur;
    return 1;
}
