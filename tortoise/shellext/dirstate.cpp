
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

#include <stdio.h>
#include <stdlib.h>
#include <stddef.h>
#include <time.h>
#include <sys/types.h>
#include <sys/stat.h>

#include <vector>
#include <list>


#ifdef WIN32

#ifndef _WINBASE_
#include <windef.h>   // needed by winbase.h
#include <stdarg.h>   // needed by winbase.h
#include <winbase.h>
#endif

#include <string.h>
#include <_mingw.h>

#define MAX_PATH          260


static __int64 days_between_epochs = 134774; /* days between 1.1.1601 and 1.1.1970 */
static __int64 secs_between_epochs = (__int64)days_between_epochs * 86400;

int lstat(const char* file, struct _stat* pstat)
{
    WIN32_FIND_DATA data;
    HANDLE hfind;
    __int64 temp;

    hfind = FindFirstFile(file, &data);
    if (hfind == INVALID_HANDLE_VALUE)
        return -1;
    FindClose(hfind);

    pstat->st_mtime = *(__int64*)&data.ftLastWriteTime / 10000000 - secs_between_epochs;
    pstat->st_size = (data.nFileSizeHigh << sizeof(data.nFileSizeHigh)) | data.nFileSizeLow;

    return 0;
}

#endif


#define HASH_LENGTH 20


struct direntry
{
    unsigned char state;
    unsigned mode;
    unsigned size;
    unsigned mtime;
    unsigned length;
    std::string name;
};


struct dirstate
{
    char parent1[HASH_LENGTH];
    char parent2[HASH_LENGTH];

    std::vector<direntry> entries;

    static std::auto_ptr<dirstate> read(const char *path);
    void add(const direntry& e) { entries.push_back(e); }

private:
    static uint32_t ntohl(uint32_t x)
    {
        return ((x & 0x000000ffUL) << 24) |
               ((x & 0x0000ff00UL) <<  8) |
               ((x & 0x00ff0000UL) >>  8) |
               ((x & 0xff000000UL) >> 24);
    }
};


class dirstatecache
{
    struct entry
    {
        const dirstate* dstate;
        __time64_t      mtime;
        std::string     path;

        entry(): dstate(0), mtime(0) {}
    };

    typedef std::list<entry>::iterator Iter;

    static std::list<entry> _cache;

public:
    static const dirstate* get(const char* hgroot);
};

std::list<dirstatecache::entry> dirstatecache::_cache;


std::auto_ptr<dirstate> dirstate::read(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f)
        return std::auto_ptr<dirstate>(0);

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

        pd->add(e);
    }

    fclose(f);

    return pd;
}


const dirstate* dirstatecache::get(const char* hgroot)
{
    std::string path = hgroot;
    path += "/.hg/dirstate";

    struct _stat stat;

    if (0 != lstat(path.c_str(), &stat))
        return 0;
    
    Iter iter = _cache.begin();

    for (;iter != _cache.end(); ++iter)
    {
        if (path == iter->path)
            break;
    }

    if (iter == _cache.end())
    {     
        entry e;
        e.path = path;
        iter = _cache.insert(iter, e);
    }

    if (iter->mtime < stat.st_mtime)
    {
        iter->mtime = stat.st_mtime;
        if (iter->dstate)
            delete iter->dstate;
        iter->dstate = dirstate::read(path.c_str()).release();
    }

    return iter->dstate;
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


char mapdirstate(const direntry* entry, const struct _stat* stat)
{
    switch (entry->state)
    {
    case 'n':
        if (entry->mtime == (unsigned)stat->st_mtime
            && entry->size == (unsigned)stat->st_size
#ifndef WIN32
            && entry->mode == stat->st_mode
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


int HgQueryDirstate(
    const char* hgroot, const char* abspath, char* relpathloc, 
    const dirstate*& ppd, struct _stat& pstat)
{
    if (0 != lstat(abspath, &pstat))
    {
        TDEBUG_TRACE("HgQueryDirstate: lstat returns non-null");
        return 0;
    }

    ppd = dirstatecache::get(hgroot);
    if (!ppd)
    {
        TDEBUG_TRACE("HgQueryDirstate: dirstatecache::get returns NULL");
        return 0;
    }

    for (char* t = relpathloc; *t; ++t)
    {
        if (*t == '\\')
            *t = '/';
    }

    return 1;
}


int HgQueryDirstateDirectory(
    const char* hgroot, char* abspath, char* relpathloc, char& outStatus)
{
    const dirstate* pd = 0;
    struct _stat stat;

    if (!HgQueryDirstate(hgroot, abspath, relpathloc, pd, stat))
        return 0;

    bool added = false;
    bool modified = false;
    bool empty = true;

    size_t rootlen = strlen(hgroot);
    size_t len = strlen(relpathloc);

    for (unsigned ix = 0; ix < pd->entries.size() && !modified; ix++)
    {
        const direntry& e = pd->entries[ix];

        if (0 != strncmp(relpathloc, e.name.c_str(), len))
            continue;
        
        empty = false;

        switch (e.state)
        {
        case 'n':
            if (!modified)
            {
                std::string temp = hgroot;
                temp += "/";
                temp += e.name;
                if (0 == lstat(temp.c_str(), &stat))
                    modified = (mapdirstate(&e, &stat) == 'M');
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


int HgQueryDirstateFile(
    const char* hgroot, const char* abspath, char* relpathloc, char& outStatus)
{
    const dirstate* pd = 0;
    struct _stat stat;

    TDEBUG_TRACE("HgQueryDirstateFile: search for " << abspath);
    TDEBUG_TRACE("HgQueryDirstateFile: hgroot = " << hgroot);

    if (!HgQueryDirstate(hgroot, abspath, relpathloc, pd, stat))
    {
        TDEBUG_TRACE("HgQueryDirstateFile: HgQueryDirstate returns false");
        return 0;
    }

    TDEBUG_TRACE("HgQueryDirstateFile: pd->entries.size() = " << pd->entries.size());
    TDEBUG_TRACE("HgQueryDirstateFile: relpathloc = " << relpathloc);

    for (unsigned ix = 0; ix < pd->entries.size(); ix++)
    {
        if (0 == strncmp(relpathloc, pd->entries[ix].name.c_str(), MAX_PATH))
        {
            TDEBUG_TRACE("HgQueryDirstateFile: found relpathloc");
            outStatus = mapdirstate(&pd->entries[ix], &stat);
            TDEBUG_TRACE("HgQueryDirstateFile: outStatus = " << outStatus);
            return outStatus != '?';
        }
    }

    return 0;
}


#if 0
int main(int argc, char *argv[])
{
    std::auto_ptr<dirstate> pd = dirstate::read(".hg/dirstate");
    time_t t;
    char *s;
    unsigned ix;
    printf("parent1: %s\n", revhash_string(pd->parent1));
    printf("parent2: %s\n", revhash_string(pd->parent2));
    printf("entries: %d\n\n", pd->entries.size());
    for (ix = 0; ix < pd->entries.size(); ++ix)
    {
        t = pd->entries[ix].mtime;
        s = ctime(&t);
        s[strlen(s) - 1] = '\0';
        printf("%s %s\n", s, pd->entries[ix].name.c_str());
    }
    return 0;
}
#endif
