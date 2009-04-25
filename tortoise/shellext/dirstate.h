#ifndef _DIRSTATE_H
#define _DIRSTATE_H

int HgQueryDirstateFile(const char* hgroot, const char* abspath, char* relpathloc, char& outStatus);

int HgQueryDirstateDirectory(const char* hgroot, char* abspath, char* relpathloc, char& outStatus);

#endif
