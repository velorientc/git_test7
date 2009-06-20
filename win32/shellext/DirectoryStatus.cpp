
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

#include "DirectoryStatus.h"
#include "Thgstatus.h"
#include "TortoiseUtils.h"


char DirectoryStatus::status(const std::string& relpath_) const
{
    char res = 'C';
    bool added = false;
    bool modified = false;

    const std::string relpath = relpath_ + '/';

    for (V::const_iterator i = v_.begin(); i != v_.end(); ++i)
    {
        const E& e = *i;
        if (relpath_.empty() ||
            e.path_.compare(0, relpath.length(), relpath) == 0)
        {
            if (e.status_ == 'm' || e.status_ == 'r')
            {
                modified = true;
                break;
            }
            if (e.status_ == 'a')
                added = true;
        }
    }

    if (modified)
        res = 'M';
    else if (added)
        res = 'A';
    else
        res = 'C';

    return res;
}


int DirectoryStatus::read(const std::string& hgroot, const std::string& cwd)
{
    v_.clear();

    std::string p = hgroot + "\\.hg\\thgstatus";

    FILE *f = fopenReadRenameAllowed(p.c_str());
    if (!f)
    {
        TDEBUG_TRACE("DirectoryStatus::read: can't open '" << p << "'");
        std::string p = (cwd.size() < hgroot.size() ? hgroot : cwd);
        Thgstatus::update(p);
        return 0;
    }

    char state;
    std::vector<char> path(MAX_PATH);

    DirectoryStatus::E e;

    while (fread(&state, sizeof(state), 1, f) == 1)
    {
        e.status_ = state;

        path.clear();
        char t;
        while (fread(&t, sizeof(t), 1, f) == 1 && t != '\n')
        {
            path.push_back(t);
            if (path.size() > 1000)
                return 0;
        }
        path.push_back('/');
        path.push_back(0);

        e.path_ = &path[0];

        v_.push_back(e);
    }

    fclose(f);

    TDEBUG_TRACE("DirectoryStatus::read(" << hgroot << "): done. "
        << v_.size() << " entries read");

    return 1;
}


struct CacheEntry
{
    std::string     hgroot_;
    DirectoryStatus ds_;
    bool            readfailed_;
    unsigned        tickcount_;

    CacheEntry(): readfailed_(false), tickcount_(0) {};
};


DirectoryStatus* DirectoryStatus::get(
    const std::string& hgroot, const std::string& cwd)
{
    static CacheEntry ce;
    
    unsigned tc = GetTickCount();

    if (ce.hgroot_ != hgroot || (tc - ce.tickcount_) > 2000)
    {
        ce.hgroot_.clear();
        ce.readfailed_ = (ce.ds_.read(hgroot, cwd) == 0);
        ce.hgroot_ = hgroot;
        ce.tickcount_ = GetTickCount();
    }

    return (ce.readfailed_ ? 0 : &ce.ds_);
}


