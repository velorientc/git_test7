
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

#include "HgRepoRoot.h"
#include "TortoiseUtils.h"


bool HgRepoRoot::is_subdir(const std::string& refp, const std::string& p)
{
    // refp = "foo\bar"
    // p    = "foo\bar\ping" -> return true

    if (refp.size() > p.size())
        return false;

    if (p.compare(0, refp.size(), refp) != 0)
        return false;

    if (refp.size() == p.size())
        return true;

    // p is longer than refp

    char c = p[refp.size()];

    // refp = "foo\bar"
    // p    = "foo\bar2", c is '2' -> return false

    if (c == '\\' || c == '/')
        return true;

    return false;
}


const std::string& HgRepoRoot::get(const std::string& path)
{
    static E cache;

    if (!cache.hgroot_.empty() 
        && is_subdir(cache.hgroot_, path))
    {
        unsigned tc = GetTickCount();
        if (tc - cache.tickcount_ < 2000)
        {
            ++cache.hitcount_;
            return cache.hgroot_;
        }
    }

    std::string r = GetHgRepoRoot(path);

    bool show_hitcount = !cache.hgroot_.empty() && cache.hitcount_ > 0;
    if (show_hitcount)
        TDEBUG_TRACE("HgRepoRoot::get: '"
            << cache.hgroot_ << "' had " << cache.hitcount_ << " hits");

    cache.hitcount_ = 0;

    if (r.empty())
    {
        cache.hgroot_.clear();
        cache.tickcount_ = 0;
    }
    else
    {
        if (show_hitcount)
        {
            const char* verb = (r != cache.hgroot_ ? "caching" : "refreshing" );
            TDEBUG_TRACE("HgRepoRoot::get: " << verb << " '" << cache.hgroot_ << "'");
        }
        cache.hgroot_ = r;
        cache.tickcount_ = GetTickCount();
    }

    return cache.hgroot_;
}
