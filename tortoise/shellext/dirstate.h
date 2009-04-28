#ifndef _DIRSTATE_H
#define _DIRSTATE_H

#include <string>

int HgQueryDirstate(const std::string& path, char& outStatus);

#endif
