
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

#ifndef _THGSTATUS_H
#define _THGSTATUS_H

#include <string>

class Thgstatus
{
    static int SendRequest(const std::string& request);

public:
    static int update(const std::string& path) {
        return SendRequest("update|" + path);
    }
    static int remove(const std::string& path) {
        return SendRequest("remove|" + path);
    }
};

#endif
