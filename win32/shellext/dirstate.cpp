
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

#include "dirstate.h"


std::auto_ptr<Dirstate> Dirstate::read(const std::string& path, bool& unset)
{
    unset = false;

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
    std::vector<char> relpath(MAX_PATH + 10, 0);
    while (e.read(f, relpath))
    {
        if (e.unset())
        {
            unset = true;
            fclose(f);
            return std::auto_ptr<Dirstate>(0);
        }

        if (e.state == 'a')
            ++pd->num_added_;

        pd->add(&relpath[0], e);
    }

    fclose(f);

    return pd;
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
    bool unset;
    std::auto_ptr<Dirstate> pd = Dirstate::read(".hg/dirstate", unset);
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
