
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

#ifndef _DIRSTATE_H
#define _DIRSTATE_H

#include "Directory.h"

#include <string>


#define HASH_LENGTH 20

class Dirstate
{
    Directory root_;

    unsigned num_added_; // number of entries that have state 'a'
    unsigned num_entries_;

public:
    char parent1[HASH_LENGTH];
    char parent2[HASH_LENGTH];

    static std::auto_ptr<Dirstate> read(const std::string& path);
    
    Directory& root() { return root_; }

    void add(const std::string& relpath, Direntry& e) {
        root_.add(relpath, e);
        ++num_entries_; 
    }
    
    unsigned num_added() const { return num_added_; }
    unsigned size() const { return num_entries_; }

private:
    Dirstate()
    : root_(0, "", ""), num_added_(0), num_entries_(0) {}
};

#endif
