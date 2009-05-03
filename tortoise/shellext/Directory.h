
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
    const std::string basepath_;

    DirsT  subdirs_;
    FilesT files_;
    
    unsigned tickcount_;
    char status_;

public:
    Directory(Directory* p, const std::string& n, const std::string& basepath): 
        parent_(p), name_(n), basepath_(basepath), tickcount_(0), status_(-1) {}

    ~Directory();

    std::string path() const;

    int add(const std::string& relpath, Direntry& e);

    const Direntry* get(const std::string& relpath) const;
    Directory* Directory::getdir(const std::string& n);

    char status(const std::string& hgroot);

    void print() const;

private:
    char status_imp(const std::string& hgroot);
};

#endif

