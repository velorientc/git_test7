
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
#include "Directory.h"
#include "TortoiseUtils.h"

#include <shlwapi.h>

#include <vector>
#include <list>


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

    Direntry e;

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
        unsigned tc0 = GetTickCount();
        iter->dstate = Dirstate::read(path).release();
        unsigned tc1 = GetTickCount();
        unsigned delta = tc1 - tc0;
        TDEBUG_TRACE("Dirstatecache::get: read done in " << delta << " ticks, "
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
        const Direntry* e = pds->root().get(relpath);
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
