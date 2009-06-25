
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

#include "InitStatus.h"


InitStatus& InitStatus::inst()
{
    static InitStatus s;
    return s;
}


void InitStatus::add(std::string& s, const char* missing)
{
    if (!s.empty())
        s += ", ";
    s += missing;
}


std::string InitStatus::check()
{
    const InitStatus& self = inst();
    std::string missing;

    if (self.unchanged_ == 0)
        add(missing, "unchanged");
    if (self.added_ == 0)
        add(missing, "added");
    if (self.modified_ == 0)
        add(missing, "modified");
    if (self.notinrepo_ == 0)
        add(missing, "notinrepo");
    
    if (missing.empty())
        return "";

    std::string res = "InitStatus: error: uninitialized handlers: ";
    res += missing;
    TDEBUG_TRACE("***** " << res);
    return res;
}
