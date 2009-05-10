#ifndef _DIRSTATE_H
#define _DIRSTATE_H

#include <string>

int HgQueryDirstate(
    const std::string& path, const char& filterStatus, char& outStatus);

#endif
