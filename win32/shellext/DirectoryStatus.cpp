
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
    noicons_ = false;

    std::string p = hgroot + "\\.hg\\thgstatus";

    FILE *f = fopenReadRenameAllowed(p.c_str());
    if (!f)
    {
        TDEBUG_TRACE("DirectoryStatus::read: can't open '" << p << "'");
        std::string p = (cwd.size() < hgroot.size() ? hgroot : cwd);
        Thgstatus::update(p);
        return 0;
    }

    DirectoryStatus::E e;

    int res = 1;
    const std::string noicons = "@@noicons";

    std::vector<char> vline(200);

    for (;;)
    {
        vline.clear();
        char t;

        for (;;)
        {
            if (fread(&t, sizeof(t), 1, f) != 1)
                goto close;
            if (t == '\n')
                break;
            vline.push_back(t);
            if (vline.size() > 1000)
            {
                res = 0;
                goto close;
            }
        }
        vline.push_back(0);

        std::string line = &vline[0];

        if (line.substr(0, noicons.size()) == noicons)
        {
            noicons_ = true;
            goto close;
        }

        if (line.empty())
            goto close;

        e.status_ = line[0];

        std::string path;
        if (line.size() > 1)
        {
            path = line.c_str() + 1;
        }
        path.push_back('/');

        e.path_ = path;

        v_.push_back(e);
    }

close:
    fclose(f);

    TDEBUG_TRACE("DirectoryStatus::read(" << hgroot << "): done. "
        << v_.size() << " entries read. noicons_ = " << noicons_ );

    return res;
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


