#ifndef _DIRSTATE_H
#define _DIRSTATE_H

#include <string>

int HgQueryDirstate(
    const std::string& hgroot, const std::string& abspath,
    const std::string& relpath, char& outStatus);

#endif
