#ifndef _DIRSTATE_H
#define _DIRSTATE_H

#include <string>

int HgQueryDirstateFile(
    const char* hgroot, const char* abspath, std::string& relpath, char& outStatus);

int HgQueryDirstateDirectory(
    const char* hgroot, const char* abspath, std::string& relpath, char& outStatus);

#endif
