
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
#include "Winstat.h"
#include "TortoiseUtils.h"
#include "Thgstatus.h"

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

    QueryState(): isdir(false), status('0'), tickcount(0) {}
};


bool hasHgDir(char cls, const std::string& path, unsigned& ticks)
{
    ticks = 0;

    bool res = false;

    if (path.empty() || path == "\\")
        return res;

    const std::string p = path + "\\.hg";

    if (::PathIsUNCServerShare(p.c_str()))
        return res;

    unsigned tc0 = ::GetTickCount();
    res = ::PathIsDirectory(p.c_str()) != 0;
    unsigned tc1 = ::GetTickCount();

    ticks = tc1 - tc0;

    if (ticks > 5 /* ms */)
    {
        // trace slower PathIsDirectory calls (untypical on local discs)
        TDEBUG_TRACE(
            "[" << cls << "] hasHgDir: PathIsDirectory(\"" << p << "\")" << 
            " -> " << res << ", in " << ticks << " ticks"
        );
    }

    return res;
}


int findHgRoot(char cls, QueryState& cur, QueryState& last, bool outdated)
{
    std::string dp = "["; dp += cls; dp += "] findHgRoot"; 

    {
        std::string p = cur.path;
        p.push_back('\\');
        if (p.find("\\.hg\\") != std::string::npos) 
        {
            // ignore files and dirs named '.hg'
            last = cur;
            return 0;
        }
    }

    if (!outdated && !last.hgroot.empty() 
        && cur.path.size() >= last.hgroot.size()
        && StartsWith(cur.path, last.hgroot + "\\"))
    {
        cur.hgroot = last.hgroot;
        return 1;
    }

    unsigned ticks = 0;
    bool file_access_is_unacceptably_slow = false;

    if (!PathIsNetworkPath(cur.path.c_str()))
    {
        // checking if we have a repo root, visible from its parent dir

        const bool has_hg = hasHgDir(cls, cur.path, ticks);

        if (ticks > 5000 /* ms */)
        {
            file_access_is_unacceptably_slow = true;
            goto exit;
        }

        if (has_hg)
        {
            cur.hgroot = cur.path;
            TDEBUG_TRACE(dp << "(" << cur.path << "): hgroot = cur.path");
            return 1;
        }
    }

    cur.basedir = DirName(cur.path);

    if (!outdated && !last.basedir.empty() && cur.basedir == last.basedir)
    {
        cur.hgroot = last.hgroot;
        return 1;
    }

    for (std::string p = cur.basedir;;)
    {
        bool has_hg = hasHgDir(cls, p, ticks);
        if (ticks > 5000 /* ms */)
        {
            const std::string reason = "ignoring slow \"" + p + "\"";
            Thgstatus::error(reason);
            file_access_is_unacceptably_slow = true;
            goto exit;
        }

        if (has_hg) 
        {
            cur.hgroot = p;
            TDEBUG_TRACE(
                dp << "(" << cur.path << "): hgroot = '" << cur.hgroot
                << "' (found repo)"
            );
            return 1;
        }
        std::string p2 = DirName(p);
        if (p2.size() == p.size())
            break;
        p.swap(p2);
    }

exit:
    if (file_access_is_unacceptably_slow)
    {
        TDEBUG_TRACE(
            "******" << dp << "(" << cur.path << "): ignored, " 
            << "call took too long (" << ticks << " ticks)");
    }
    else
    {
        TDEBUG_TRACE(dp << "(" << cur.path << "): NO repo found");
    }
    last = cur;
    return 0;
}


int get_relpath(
    const std::string& hgroot, 
    const std::string& path,
    std::string& res
)
{
    size_t offset = hgroot.size();
    if (offset == 0)
        return 0;

    if (offset > path.size())
        return 0;

    if (path[offset] == '\\')
        offset++;
    
    const char* relpathptr = path.c_str() + offset;

    res = relpathptr;
    return 1;
}


int HgQueryDirstate(
    const char cls,
    const std::string& path,
    const char& filterStatus, 
    char& outStatus
)
{
    std::string dp = "["; dp += cls; dp += "] HgQueryDirstate: "; 

    static QueryState last;

    if (path.empty())
        return 0;

    QueryState cur;

    cur.path = path;
    cur.tickcount = ::GetTickCount();

    const bool outdated = cur.tickcount - last.tickcount > 2000;

    if (!outdated && last.path == path) 
    {
        outStatus = last.status;
        if (outStatus == 'P')
            outStatus = 'M';
        return 1;
    }

    if (::PathIsRoot(path.c_str()))
    {
        last = cur;
        return 0;
    }

    if (findHgRoot(cls, cur, last, outdated) == 0)
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

    DirectoryStatus* pdirsta = DirectoryStatus::get(cur.hgroot, cur.basedir);
    if (pdirsta && pdirsta->noicons())
    {
        last = cur;
        return 0;
    }

    if (relpath.empty())
    {
        outStatus = (pdirsta ? pdirsta->status(relpath) : '?');
        cur.status = outStatus;
        cur.tickcount = ::GetTickCount();
        last = cur;
        return 1;
    }

    bool unset = false;

    Dirstate* pds = Dirstatecache::get(cur.hgroot, cur.basedir, unset);
    if (!pds)
    {
        TDEBUG_TRACE(
            dp << "Dirstatecache::get(" << cur.hgroot 
            << ") returns no Dirstate"
        );
        last = cur;
        return 0;
    }

    Winstat stat;
    if (0 != stat.lstat(path.c_str())) 
    {
        TDEBUG_TRACE(dp << "lstat(" << path << ") failed");
        last = cur;
        return 0;
    }
    cur.isdir = stat.isdir;
#if 0
    TDEBUG_TRACE(
        dp << "stat.lstat(\"" << cur.path << "\") "
        << "-> stat.isdir is " << stat.isdir
    );
#endif

    if (cur.isdir)
    {
        if (!relpath.empty() && !pds->root().getdir(relpath))
        {
            last = cur;
            return 0;  // unknown dir -> no icon
        }

        outStatus = (pdirsta ? pdirsta->status(relpath) : '?');
        cur.status = outStatus;
        cur.tickcount = ::GetTickCount();
        last = cur;
        return 1;
    }

    const Direntry* const e = pds->root().get(relpath);
    if (!e) 
    {
        last = cur;
        return 0;
    }

    outStatus = e->status(stat);

    if (unset)
        goto exit;

    bool update = false;

    if (outStatus == 'M')
    {
        std::string relbase;
        if (pdirsta && get_relpath(cur.hgroot, cur.basedir, relbase))
        {
            TDEBUG_TRACE(dp << "relbase = '" << relbase << "'");

            char basedir_status = pdirsta->status(relbase);
            TDEBUG_TRACE(dp << "basedir_status = " << basedir_status);

            if (basedir_status != 'M')
                update = true;
        }        
    }
    else if (outStatus == 'P')
    {
        static unsigned lasttickcount;

        const unsigned tc = ::GetTickCount();
        const bool outdated = tc - lasttickcount > 6000;

        if (outdated) // protect against endless update loops
        {
            update = true;
            lasttickcount = tc;
        }

        TDEBUG_TRACE(dp << "outStatus is 'P'");
    }

    if (update)
    {
        TDEBUG_TRACE(dp << "calling Thgstatus::update");
        Thgstatus::update(path);
    }

  exit:
    cur.status = outStatus;
    if (outStatus == 'P')
        outStatus = 'M';
    cur.tickcount = ::GetTickCount();
    last = cur;
    return 1;
}
