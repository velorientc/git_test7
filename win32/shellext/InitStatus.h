
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

class InitStatus
{
public:
    int unchanged_;
    int added_;
    int modified_;
    int notinrepo_;

    static InitStatus& inst();
    static std::string check();

private:
    InitStatus()
    : unchanged_(0), added_(0), modified_(0), notinrepo_(0) {}

    static void add(std::string& s, const char* missing);
};
