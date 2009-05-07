
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

#include <string>
#include <vector>


class DirectoryStatus
{
    struct E
    {
        std::string path_;
        char status_;

        E(): status_(0) {}
    };

    typedef std::vector<E> V;
    V v_;

public:
    static DirectoryStatus* get(const std::string& hgroot);
    char status(const std::string& relpath) const;

private:
    int read(const std::string& hgroot);
};
