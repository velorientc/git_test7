#ifndef _DIRSTATE_H
#define _DIRSTATE_H

#include <string>

int HgQueryDirstateFile(
    const std::string& hgroot, const std::string& abspath,
    std::string& relpath, char& outStatus);

int HgQueryDirstateDirectory(
    const std::string& hgroot, const std::string& abspath,
    std::string& relpath, char& outStatus);

#endif
