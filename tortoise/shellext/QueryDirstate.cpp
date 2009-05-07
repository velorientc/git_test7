
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
#include "TortoiseUtils.h"
#include "Winstat.h"

#include <shlwapi.h>


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

    if (PathIsDirectory(path.c_str()))
    {
        DirectoryStatus* pds = DirectoryStatus::get(hgroot);
        if (!pds)
            return 0;

        outStatus = pds->status(relpath);
    }
    else
    {
        Dirstate* pds = Dirstatecache::get(hgroot);
        if (!pds)
        {
            TDEBUG_TRACE("HgQueryDirstate: Dirstatecache::get(" 
                << hgroot << ") returns no Dirstate");
            return 0;
        }

        if (filterStatus == 'A' && pds->num_added() == 0)
            return 0;

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
