
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


char DirectoryStatus::status(const std::string& relpath) const
{
    TDEBUG_TRACE("DirectoryStatus::status(" << relpath << ")");

    char res = 'C';
    bool added = false;
    bool modified = false;

    for (V::const_iterator i = v_.begin(); i != v_.end(); ++i)
    {
        const E& e = *i;
        if (e.path_.compare(0, relpath.length(), relpath) == 0)
        {
            TDEBUG_TRACE("DirectoryStatus::status(" << relpath << "):"
                << " found '" << e.path_ << "'");
            if (e.status_ == 'r' || e.status_ == 'm')
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

    TDEBUG_TRACE("DirectoryStatus::status(" << relpath << "): returns " << res);
    return res;
}


int DirectoryStatus::read(const std::string& hgroot)
{
    v_.clear();

    std::string p = hgroot + "\\.hg\\thgstatus";

    FILE *f = fopen(p.c_str(), "rb");
    if (!f)
    {
        TDEBUG_TRACE("DirectoryStatus::read: can't open " << p);
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
        path.push_back(0);

        e.path_ = &path[0];

        v_.push_back(e);
    }

    fclose(f);

    TDEBUG_TRACE("DirectoryStatus::read(" << hgroot << "): done. "
        << v_.size() << " entries read");

    return 1;
}
