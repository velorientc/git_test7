
// Copyright (C) 2009 Benjamin Pollack
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

#include "dirstate.h"
#include "TortoiseUtils.h"

#include <shlwapi.h>

#include <vector>
#include <list>


#ifdef WIN32

static __int64 days_between_epochs = 134774; /* days between 1.1.1601 and 1.1.1970 */
static __int64 secs_between_epochs = (__int64)days_between_epochs * 86400;

int lstat(const char* file, struct _stat& rstat)
{
    WIN32_FIND_DATA data;
    HANDLE hfind;
    __int64 temp;

    hfind = FindFirstFile(file, &data);
    if (hfind == INVALID_HANDLE_VALUE)
        return -1;
    FindClose(hfind);

    rstat.st_mtime = *(__int64*)&data.ftLastWriteTime / 10000000 - secs_between_epochs;
    rstat.st_size = (data.nFileSizeHigh << sizeof(data.nFileSizeHigh)) | data.nFileSizeLow;

    return 0;
}

#endif


struct direntry
{
    unsigned char state;
    unsigned mode;
    unsigned size;
    unsigned mtime;
    unsigned length;
    
    std::string name;

    char status(const struct _stat& stat) const;
};


char direntry::status(const struct _stat& stat) const
{
    switch (this->state)
    {
    case 'n':
        if (this->mtime == (unsigned)stat.st_mtime
            && this->size == (unsigned)stat.st_size
#ifndef WIN32
            && this->mode == stat.st_mode
#endif
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


class Directory
{
    typedef std::vector<Directory*> DirsT;
    typedef std::vector<direntry> FilesT;
    
    Directory* parent_;
    std::string name_;

    DirsT  subdirs_;
    FilesT files_;
    
    unsigned tickcount_;
    char status_;

public:
    Directory(Directory* p, const std::string& n): 
        parent_(p), name_(n), tickcount_(0), status_(-1) {}
    ~Directory();

    std::string path(const std::string& n = "") const;

    int add(const std::string& relpath, direntry& e);

    const direntry* get(const std::string& relpath) const;
    Directory* Directory::getdir(const std::string& n);

    char status(const std::string& hgroot);

    void print() const;

private:
    char status_imp(const std::string& hgroot);
};


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


int Directory::add(const std::string& n, direntry& e)
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


const direntry* Directory::get(const std::string& n) const
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
        std::string p =  hrs + path(i->name);

        if (0 != lstat(p.c_str(), stat))
        {
            TDEBUG_TRACE("Directory(" << path() 
                << ")::status_imp: lstat(" << p << ") failed");
            continue;
        }

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

    void add(const std::string& relpath, direntry& e) {
        root_.add(relpath, e);
        ++num_entries_; 
    }
    
    unsigned num_added() const { return num_added_; }
    unsigned size() const { return num_entries_; }

private:
    Dirstate()
    : root_(0, ""), num_added_(0), num_entries_(0) {}

    static uint32_t ntohl(uint32_t x)
    {
        return ((x & 0x000000ffUL) << 24) |
               ((x & 0x0000ff00UL) <<  8) |
               ((x & 0x00ff0000UL) >>  8) |
               ((x & 0xff000000UL) >> 24);
    }
};


std::auto_ptr<Dirstate> Dirstate::read(const std::string& path)
{
    FILE *f = fopen(path.c_str(), "rb");
    if (!f)
    {
        TDEBUG_TRACE("Dirstate::read: can't open " << path);
        return std::auto_ptr<Dirstate>(0);
    }

    std::auto_ptr<Dirstate> pd(new Dirstate());

    fread(&pd->parent1, sizeof(char), HASH_LENGTH, f);
    fread(&pd->parent2, sizeof(char), HASH_LENGTH, f);

    direntry e;

    std::vector<char> temp(MAX_PATH+10, 0);

    while (fread(&e.state, sizeof(e.state), 1, f) == 1)
    {
        fread(&e.mode, sizeof(e.mode), 1, f);
        fread(&e.size, sizeof(e.size), 1, f);
        fread(&e.mtime, sizeof(e.mtime), 1, f);
        fread(&e.length, sizeof(e.length), 1, f);

        e.mode = ntohl(e.mode);
        e.size = ntohl(e.size);
        e.mtime = ntohl(e.mtime);
        e.length = ntohl(e.length);

        temp.resize(e.length+1, 0);
        fread(&temp[0], sizeof(char), e.length, f);
        temp[e.length] = 0;

        if (e.state == 'a')
            ++pd->num_added_;

        pd->add(&temp[0], e);
    }

    fclose(f);

    return pd;
}


class Dirstatecache
{
    struct entry
    {
        Dirstate*       dstate;
        __time64_t      mtime;
        std::string     hgroot;
        unsigned        tickcount;

        entry(): dstate(0), mtime(0), tickcount(0) {}
    };

    typedef std::list<entry>::iterator Iter;

    static std::list<entry> _cache;

public:
    static Dirstate* get(const std::string& hgroot);
};

std::list<Dirstatecache::entry> Dirstatecache::_cache;


Dirstate* Dirstatecache::get(const std::string& hgroot)
{
    Iter iter = _cache.begin();

    for (;iter != _cache.end(); ++iter)
    {
        if (hgroot == iter->hgroot)
            break;
    }

    bool isnew = false;

    if (iter == _cache.end())
    {
        if (_cache.size() >= 10)
        {
            TDEBUG_TRACE("Dirstatecache::get: dropping " << _cache.back().hgroot);
            delete _cache.back().dstate;
            _cache.back().dstate = 0;
            _cache.pop_back();
        }
        entry e;
        e.hgroot = hgroot;
        _cache.push_front(e);
        iter = _cache.begin();
        isnew = true;
    }

    unsigned tc = GetTickCount();

    std::string path = hgroot + "\\.hg\\dirstate";

    struct _stat stat;

    bool stat_done = false;

    if (isnew || (tc - iter->tickcount) > 500)
    {
        if (0 != lstat(path.c_str(), stat))
        {
            TDEBUG_TRACE("Dirstatecache::get: lstat(" << path <<") failed");
            return 0;
        }
        iter->tickcount = tc;
        stat_done = true;
        TDEBUG_TRACE("Dirstatecache::get: lstat(" << path <<") ok ");
    }

    if (stat_done && iter->mtime < stat.st_mtime)
    {
        iter->mtime = stat.st_mtime;
        if (iter->dstate) {
            delete iter->dstate;
            iter->dstate = 0;
            TDEBUG_TRACE("Dirstatecache::get: refreshing " << hgroot);
        } else {
            TDEBUG_TRACE("Dirstatecache::get: reading " << hgroot);
        }
        iter->dstate = Dirstate::read(path).release();
        TDEBUG_TRACE("Dirstatecache::get: "
            << _cache.size() << " repos in cache");
    }

    return iter->dstate;
}


int HgQueryDirstate(
    const std::string& path, const char& filterStatus, char& outStatus)
{
    if (PathIsRoot(path.c_str()))
        return 0;

    std::string hgroot = GetHgRepoRoot(path);
    if (hgroot.empty())
        return 0;

    size_t offset = hgroot.length();
    if (path[offset] == '\\')
        offset++;
    const char* relpathptr = path.c_str() + offset;

    std::string relpath = relpathptr;

    if (relpath.empty())
        return 0; // don't show icon on repo root dir

    if (relpath == ".hg" 
            || (relpath.size() > 4 && relpath.compare(0, 4, ".hg/") == 0))
        return 0; // don't descend into .hg dir

    Dirstate* pds = Dirstatecache::get(hgroot);
    if (!pds)
    {
        TDEBUG_TRACE("HgQueryDirstate: Dirstatecache::get(" << hgroot << ") returns 0");
        return 0;
    }

    if (filterStatus == 'A' && pds->num_added() == 0)
        return 0;

    for (size_t i = 0; i < relpath.size(); ++i)
    {
        if (relpath[i] == '\\')
            relpath[i] = '/';
    }

    if (PathIsDirectory(path.c_str()))
    {
        Directory* dir = pds->root().getdir(relpath);
        if (!dir)
            return 0;
        outStatus = dir->status(hgroot);
    }
    else
    {
        const direntry* e = pds->root().get(relpath);
        if (!e)
            return 0;

        struct _stat stat;
        if (0 != lstat(path.c_str(), stat)) {
            TDEBUG_TRACE("HgQueryDirstate: lstat(" << path << ") failed");
            return 0;
        }

        outStatus = e->status(stat);
    }

    return 1;
}


static char *revhash_string(const char revhash[HASH_LENGTH])
{
    unsigned ix;
    static char rev_string[HASH_LENGTH * 2 + 1];
    static char *hexval = "0123456789abcdef";
    for (ix = 0; ix < HASH_LENGTH; ++ix)
    {
        rev_string[ix * 2] = hexval[(revhash[ix] >> 4) & 0xf];
        rev_string[ix * 2 + 1] = hexval[revhash[ix] & 0xf];
    }
    rev_string[sizeof(rev_string)] = 0;
    return rev_string;
}


void testread()
{
    std::auto_ptr<Dirstate> pd = Dirstate::read(".hg/dirstate");
    if (!pd.get()) {
        printf("error: could not read .hg/dirstate\n");
        return;
    }
    time_t t;
    char *s;
    unsigned ix;
    printf("parent1: %s\n", revhash_string(pd->parent1));
    printf("parent2: %s\n", revhash_string(pd->parent2));
    printf("entries: %d\n\n", pd->size());

    pd->root().print();
}


#ifdef APPMAIN
int main(int argc, char *argv[])
{
    testread();
    return 0;
}
#endif
