
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

#include <time.h>

#include "stdafx.h"

#include "Directory.h"
#include "Winstat.h"


Directory::Directory(
    Directory* p, const std::string& n, const std::string& basepath
):
    parent_(p), name_(n)
{
    if (n.empty())
        path_ = basepath;
    else if (basepath.empty())
        path_ = n;
    else
        path_ = basepath + '/' + n;
}


Directory::~Directory()
{
    for (DirsT::iterator i = subdirs_.begin(); i != subdirs_.end(); ++i)
    {
        delete *i;
    }
}


int splitbase(const std::string& n, std::string& base, std::string& rest)
{
    if (n.empty())
        return 0;

    size_t x = n.find_first_of ('/');
    if (x == std::string::npos)
    {
        base.clear();
        rest = n;
        return 1;
    }

    if (x == 0 || x == n.length()-1)
        return 0;

    base = n.substr(0, x);
    rest = n.substr(x+1);

    return 1;
}


int Directory::add(const std::string& n_in, Direntry& e)
{
    std::string base;
    std::string rest;
    
    std::string n = n_in;
    Directory* cur = this;
    
    for (;;)
    {

        if (!splitbase(n, base, rest)) {
            TDEBUG_TRACE("Directory(" << path() << ")::add(" << n_in 
                << "): splitbase returned 0");
            return 0;
        }

        if (base.empty())
        {
            e.name = n;
            cur->files_.push_back(e);
            return 1;
        }

        Directory* d = 0;
        for (DirsT::iterator i = cur->subdirs_.begin(); 
                i != cur->subdirs_.end(); ++i)
        {
            if ((*i)->name_ == base) {
                d = *i;
                break;
            }
        }

        if (!d)
        {
            d = new Directory(cur, base, cur->path());
            cur->subdirs_.push_back(d);
        }

        n = rest;
        cur = d;
    }
}


const Direntry* Directory::get(const std::string& n_in) const
{
    std::string base;
    std::string rest;

    std::string n = n_in;
    const Directory* cur = this;

    for (;;)
    {
        loopstart:

        if (!splitbase(n, base, rest))
        {
            TDEBUG_TRACE("Directory(" << path() << ")::get(" 
                << n_in << "): splitbase returned 0");
            return 0;
        }

        if (base.empty())
        {
            for (FilesT::const_iterator i = cur->files_.begin();
                    i != cur->files_.end(); ++i)
            {
                if (i->name == n)
                    return &(*i);
            }
            return 0;
        }

        for (DirsT::const_iterator i = cur->subdirs_.begin();
                i != cur->subdirs_.end(); ++i)
        {
            if ((*i)->name_ == base)
            {
                cur = *i;
                n = rest;
                goto loopstart;
            }
        }

        return 0;
    }
}


Directory* Directory::getdir(const std::string& n_in)
{
    std::string base;
    std::string rest;

    std::string n = n_in;
    const Directory* cur = this;

    for (;;)
    {
        loopstart:

        if (!splitbase(n, base, rest))
        {
            TDEBUG_TRACE("Directory(" << path() << ")::getdir("
                << n_in << "): splitbase returned 0");
            return 0;
        }

        const bool leaf = base.empty();
        const std::string& searchstr = (leaf ? n : base);

        for (DirsT::const_iterator i = cur->subdirs_.begin();
                i != cur->subdirs_.end(); ++i)
        {
            if ((*i)->name_ == searchstr)
            {
                if (leaf)
                    return *i;
                cur = *i;
                n = rest;
                goto loopstart;
            }
        }

        return 0;
    }
}


void Directory::print() const
{
    for (DirsT::const_iterator i = subdirs_.begin(); i != subdirs_.end(); ++i)
    {
        const Directory* d = *i;
        if (!d)
        {
            TDEBUG_TRACE("Directory(" << path() << ")::print: error: d is 0");
            return;
        }
        d->print();
    }

    std::string base = path();

    time_t t;
    std::string s;
    char* ctime_res = 0;

    for (FilesT::const_iterator i = files_.begin(); i != files_.end(); ++i)
    {
        std::string p = (!base.empty() ? base + "/" + i->name : i->name);
        t = i->mtime;
        ctime_res = ctime(&t);
        if (ctime_res) {
            s = ctime_res;
            s.resize(s.size() - 1); // strip ending '\n'
        }
        else {
            s = "unset";
        }
        printf(
            "%c %6o %10u %-24s %s\n", 
            i->state, i->mode, i->size, s.c_str(), p.c_str()
        );
    }
}
