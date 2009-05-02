
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

#include "stdafx.h"

#include "Directory.h"

#include <shlwapi.h>


int lstat(const char* file, struct _stat& rstat)
{
    const __int64 days_between_epochs = 134774L; /* days between 1.1.1601 and 1.1.1970 */
    const __int64 secs_between_epochs = (__int64)days_between_epochs * 86400L;
    const __int64 divisor = 10000000L;

    WIN32_FIND_DATAA data;
    HANDLE hfind;

    hfind = FindFirstFileA(file, &data);
    if (hfind == INVALID_HANDLE_VALUE)
        return -1;
    FindClose(hfind);

    rstat.st_mtime = *(__int64*)&data.ftLastWriteTime / divisor - secs_between_epochs;
    rstat.st_size = (data.nFileSizeHigh << sizeof(data.nFileSizeHigh)) | data.nFileSizeLow;

    return 0;
}


char Direntry::status(const struct _stat& stat) const
{
    switch (this->state)
    {
    case 'n':
        if (this->mtime == (unsigned)stat.st_mtime
            && this->size == (unsigned)stat.st_size
            )
            return 'C';
        else
            return 'M';
    case 'm':
        return 'M';
    case 'r':
        return 'R';
    case 'a':
        return 'A';
    default:
        return '?';
    }
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


int Directory::add(const std::string& n, Direntry& e)
{
    std::string base;
    std::string rest;

    if (!splitbase(n, base, rest)) {
        TDEBUG_TRACE("Directory(" << path() << ")::add(" << n << "): splitbase returned 0");
        return 0;
    }

    if (base.empty())
    {
        e.name = n;
        files_.push_back(e);
        return 1;
    }

    Directory* d = 0;
    for (DirsT::iterator i = subdirs_.begin(); i != subdirs_.end(); ++i)
    {
        if ((*i)->name_ == base) {
            d = *i;
            break;
        }
    }

    if (!d)
    {
        d = new Directory(this, base);
        subdirs_.push_back(d);
    }

    return d->add(rest, e);
}


const Direntry* Directory::get(const std::string& n) const
{
    std::string base;
    std::string rest;

    if (!splitbase(n, base, rest))
    {
        TDEBUG_TRACE("Directory(" << path() << ")::get(" << n << "): splitbase returned 0");
        return 0;
    }

    if (base.empty())
    {
        for (FilesT::const_iterator i = files_.begin(); i != files_.end(); ++i)
        {
            if (i->name == n)
                return &(*i);
        }
        return 0;
    }

    for (DirsT::const_iterator i = subdirs_.begin(); i != subdirs_.end(); ++i)
    {
        if ((*i)->name_ == base)
            return (*i)->get(rest);
    }

    TDEBUG_TRACE("Directory(" << path() << ")::get(" << n << "): unknown subdir");
    return 0;
}


Directory* Directory::getdir(const std::string& n)
{
    std::string base;
    std::string rest;

    if (!splitbase(n, base, rest))
    {
        TDEBUG_TRACE("Directory(" << path() << ")::getdir(" << n << "): splitbase returned 0");
        return 0;
    }

    const bool leaf = base.empty();
    const std::string& searchstr = (leaf ? n : base);

    for (DirsT::const_iterator i = subdirs_.begin(); i != subdirs_.end(); ++i)
    {
        if ((*i)->name_ == searchstr)
        {
            if (leaf)
                return *i;
            return (*i)->getdir(rest);
        }
    }

    return 0;
}


std::string Directory::path(const std::string& n) const
{
    if (name_.empty())
        return n;
    std::string res = name_;
    if (!n.empty())
        res += "/" + n;
    if (!parent_)
        return res;
    return parent_->path(res);
}


char Directory::status_imp(const std::string& hgroot)
{
    bool added = false;

    for (DirsT::iterator i = subdirs_.begin(); i != subdirs_.end(); ++i)
    {
        char s = (*i)->status_imp(hgroot);
        if (s == 'M')
            return 'M';
        if (s == 'A')
            added = true;
    }

    struct _stat stat;
    const std::string hrs = hgroot + '\\';
    for (FilesT::iterator i = files_.begin(); i != files_.end(); ++i)
    {
        if (i->state == 'r')
            return 'M'; // file was removed, report dir as modified

        std::string p =  hrs + path(i->name);

        if (0 != lstat(p.c_str(), stat))
            return 'M'; // file is missing, report dir as modified

        char s = i->status(stat);

        if (s == 'M')
            return 'M';
        if (s == 'A')
            added = true;
    }

    if (added)
        return 'A';

    return 'C';
}


char Directory::status(const std::string& hgroot)
{
    if (status_ != -1)
    {
        unsigned tc = GetTickCount();
        if (tc - tickcount_ < 3000) {
            return status_;
        }
    }

    status_ = status_imp(hgroot);
    tickcount_ = GetTickCount();

    return status_;
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
            i->state, i->mode, i->length, s.c_str(), p.c_str()
        );
    }
}
