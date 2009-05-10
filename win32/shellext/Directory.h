
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

#ifndef DIRECTORY_H
#define DIRECTORY_H

#include "Direntry.h"

#include <vector>
#include <string>


class Directory
{
    typedef std::vector<Directory*> DirsT;
    typedef std::vector<Direntry> FilesT;

    Directory* const parent_;
    const std::string name_;
    std::string path_;

    DirsT  subdirs_;
    FilesT files_;

public:
    Directory(Directory* p, const std::string& n, const std::string& basepath);
    ~Directory();

    const std::string& path() const { return path_; }

    int add(const std::string& relpath, Direntry& e);

    const Direntry* get(const std::string& relpath) const;
    Directory* Directory::getdir(const std::string& n);

    void print() const;
};

#endif

