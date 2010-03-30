#ifndef _QUERY_DIRSTATE_H
#define _QUERY_DIRSTATE_H

#include <string>

int HgQueryDirstate(
    const char myClass,
    const std::string& path,
    const char& filterStatus, 
    char& outStatus
);

#endif
