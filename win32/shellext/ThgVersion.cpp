#include "ThgVersion.h"
#include "parentid.h"

#define TOSTR(x)  L ## #x
#define TOSTR2(x) TOSTR(x)

#define THG_PARENT_ID_STRING  TOSTR2(THG_PARENT_ID)

std::wstring ThgVersion::get()
{
    return THG_PARENT_ID_STRING;
}
