
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
#include <deque>


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


#define HASH_LENGTH 20


class dirstate
{
    typedef std::deque<direntry> EntriesT;

    EntriesT entries;
    
    unsigned num_added_; // number of entries that have state 'a'

public:
    typedef EntriesT::size_type size_type;
    typedef EntriesT::const_iterator Iter;

    char parent1[HASH_LENGTH];
    char parent2[HASH_LENGTH];

    static std::auto_ptr<dirstate> read(const std::string& path);

    void add(const direntry& e) { entries.push_back(e); }

    Iter begin() const { return entries.begin(); }
    Iter end() const { return entries.end(); }
    size_type size() const { return entries.size(); }
    
    unsigned num_added() const { return num_added_; }

private:
    dirstate(): num_added_(0) {}

    static uint32_t ntohl(uint32_t x)
    {
        return ((x & 0x000000ffUL) << 24) |
               ((x & 0x0000ff00UL) <<  8) |
               ((x & 0x00ff0000UL) >>  8) |
               ((x & 0xff000000UL) >> 24);
    }
};


std::auto_ptr<dirstate> dirstate::read(const std::string& path)
{
    FILE *f = fopen(path.c_str(), "rb");
    if (!f)
    {
        TDEBUG_TRACE("dirstate::read: can't open " << path);
        return std::auto_ptr<dirstate>(0);
    }

    std::auto_ptr<dirstate> pd(new dirstate());

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

        e.name = &temp[0];

        if (e.state == 'a')
            ++pd->num_added_;

        pd->add(e);
    }

    fclose(f);

    return pd;
}


class dirstatecache
{
    struct entry
    {
        const dirstate* dstate;
        __time64_t      mtime;
        std::string     hgroot;

        entry(): dstate(0), mtime(0) {}
    };

    typedef std::list<entry>::iterator Iter;

    static std::list<entry> _cache;

public:
    static const dirstate* get(const std::string& hgroot);
};

std::list<dirstatecache::entry> dirstatecache::_cache;


const dirstate* dirstatecache::get(const std::string& hgroot)
{
    std::string path = hgroot;
    path += "/.hg/dirstate";

    struct _stat stat;

    if (0 != lstat(path.c_str(), stat))
    {
        TDEBUG_TRACE("dirstatecache::get: lstat(" << path <<") fails");
        return 0;
    }

    Iter iter = _cache.begin();

    for (;iter != _cache.end(); ++iter)
    {
        if (hgroot == iter->hgroot)
            break;
    }

    if (iter == _cache.end())
    {
        if (_cache.size() >= 10)
        {
            TDEBUG_TRACE("dirstatecache::get: dropping " << _cache.back().hgroot);
            delete _cache.back().dstate;
            _cache.back().dstate = 0;
            _cache.pop_back();
        }
        entry e;
        e.hgroot = hgroot;
        _cache.push_front(e);
        iter = _cache.begin();
    }

    if (iter->mtime < stat.st_mtime)
    {
        iter->mtime = stat.st_mtime;
        if (iter->dstate) {
            delete iter->dstate;
            iter->dstate = 0;
            TDEBUG_TRACE("dirstatecache::get: refreshing " << hgroot);
        } else {
            TDEBUG_TRACE("dirstatecache::get: reading " << hgroot);
        }
        iter->dstate = dirstate::read(path).release();
        TDEBUG_TRACE("dirstatecache::get: "
            << iter->dstate->size() << " entries read. "
            << _cache.size() << " repos in cache");
    }

    return iter->dstate;
}


static int HgQueryDirstateDirectory(
    const std::string& hgroot, const dirstate& ds,
    const std::string& relpath, char& outStatus)
{
    bool added = false;
    bool modified = false;
    bool empty = true;

    const size_t len = relpath.size();
    const std::string hgroot_slash = hgroot + "/";

    struct _stat stat;

    for (dirstate::Iter iter = ds.begin();
         iter != ds.end() && !modified; ++iter)
    {
        const direntry& e = *iter;

        if (e.name.compare(0, len, relpath) != 0)
            continue;

        empty = false;

        switch (e.state)
        {
        case 'n':
            {
                std::string temp = hgroot_slash + e.name;
                if (0 == lstat(temp.c_str(), stat))
                    modified = (e.status(stat) == 'M');
            }
            break;
        case 'm':
            modified = true;
            break;
        case 'a':
            added = true;
            break;
        }
    }

    if (modified)
        outStatus = 'M';
    else if (added)
        outStatus = 'A';
    else if (empty)
        outStatus = '?';
    else
        outStatus = 'C';

    return 1;
}


static int HgQueryDirstateFile(
    const dirstate& ds, const std::string& relpath, 
    const struct _stat& stat, char& outStatus)
{
    for (dirstate::Iter iter = ds.begin(); iter != ds.end(); ++iter)
    {
        const direntry& e = *iter;

        if (relpath == e.name)
        {
            outStatus = e.status(stat);
            return outStatus != '?';
        }
    }

    return 0;
}


int HgQueryDirstate(
    const std::string& path, const char& filterStatus, char& outStatus)
{
    struct _stat stat;
    if (0 != lstat(path.c_str(), stat))
    {
        TDEBUG_TRACE("HgQueryDirstate: lstat(" << path << ") fails");
        return 0;
    }

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

    bool isdir = PathIsDirectory(path.c_str());

    if (isdir && relpath.size() >= 3 && relpath.compare(0, 3, ".hg") == 0)
        return 0; // don't descend into .hg dir

    const dirstate* pds = dirstatecache::get(hgroot);
    if (!pds)
    {
        TDEBUG_TRACE("HgQueryDirstate: dirstatecache::get(" << hgroot << ") returns 0");
        return 0;
    }

    if (filterStatus == 'A' && pds->num_added() == 0)
        return 0;

    for (size_t i = 0; i < relpath.size(); ++i)
    {
        if (relpath[i] == '\\')
            relpath[i] = '/';
    }

    int res = 0;

    if (isdir)
        res = HgQueryDirstateDirectory(hgroot, *pds, relpath, outStatus);
    else 
        res = HgQueryDirstateFile(*pds, relpath, stat, outStatus);

    return res;
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
    std::auto_ptr<dirstate> pd = dirstate::read(".hg/dirstate");
    time_t t;
    char *s;
    unsigned ix;
    printf("parent1: %s\n", revhash_string(pd->parent1));
    printf("parent2: %s\n", revhash_string(pd->parent2));
    printf("entries: %d\n\n", pd->size());
    for (dirstate::Iter i = pd->begin(); i != pd->end(); ++i)
    {
        t = i->mtime;
        s = ctime(&t);
        s[strlen(s) - 1] = '\0';
        printf("%s %s\n", s, i->name.c_str());
    }
}


#if 0
int main(int argc, char *argv[])
{
    testread();
    return 0;
}
#endif
