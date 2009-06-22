#ifndef _TORTOISE_UTILS_H_
#define _TORTOISE_UTILS_H_

#include <malloc.h>
#include <windows.h>
#include <string>

#define _MBSTR(wstr) hf_wctomb((LPSTR)alloca(wcslen(wstr) + 1), (wstr),wcslen(wstr) + 1)
#define _WCSTR(str) hf_mbtowc((LPWSTR)alloca((strlen(str) + 1) * sizeof(WCHAR)),(str),strlen(str) + 1)

LPWSTR hf_mbtowc(LPWSTR lpw, LPCSTR lpa, int nChars);
LPSTR hf_wctomb(LPSTR lpa, LPCWSTR lpw, int nChars);

std::string GetTHgProgRoot();
std::string GetTHgShellRoot();
std::string GetTemporaryFile(LPCSTR prefix="THG");
bool IsDirectory(const std::string&);
std::string DirName(const std::string&);
std::string BaseName(const std::string&);
bool LaunchCommand(const std::string& command, const std::string& cwd);
HICON GetTortoiseIcon(const std::string & iconname);
std::string GetHgRepoRoot(const std::string& path);
bool IsHgRepo(const std::string& path);
int GetRegistryConfig(const std::string& name, std::string& res);
FILE* fopenReadRenameAllowed(const char* path);

#endif
