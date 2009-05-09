
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

#ifndef _HG_REPO_ROOT_H
#define _HG_REPO_ROOT_H

class HgRepoRoot
{
    struct E
    {
        std::string hgroot_;
        unsigned    tickcount_;
        unsigned    hitcount_;
        E(): tickcount_(0), hitcount_(0) {}
    };
    
    // true, if p is a subdir of refp, or identical
    static bool is_subdir(const std::string& refp, const std::string& p);

public:
    static const std::string& get(const std::string& path);
};

#endif
