#ifndef _TORTOISE_UTILS_H_
#define _TORTOISE_UTILS_H_

#include <malloc.h>
#include <windows.h>
#include <string>
#include <vector>

#define _WCSTR(str) hf_mbtowc((LPWSTR)alloca((strlen(str) + 1) * sizeof(WCHAR)),(str),strlen(str) + 1)

LPWSTR hf_mbtowc(LPWSTR lpw, LPCSTR lpa, int nChars);

std::string GetTHgProgRoot();
std::string GetTemporaryFile(LPCSTR prefix="THG");
bool IsDirectory(const std::string&);
std::string DirName(const std::string&);
std::string BaseName(const std::string&);
bool LaunchCommand(const std::string& command, const std::string& cwd);
HICON GetTortoiseIcon(const std::string & iconname);
std::string GetHgRepoRoot(const std::string& path);
bool IsHgRepo(const std::string& path);
FILE* fopenReadRenameAllowed(const char* path);
int GetRegSZValueW(HKEY hkey, const wchar_t* name, std::wstring& res);
bool StartsWith(const std::string& a, const std::string& b);
void Tokenize(const std::string& str, std::vector<std::string>& tokens,
  const std::string& delimiters = " ");

template <typename C, typename T>
bool contains(const C& c, const T& t)
{
    for (C::const_iterator i = c.begin(); i != c.end(); ++i)
    {
        if (*i == t)
            return true;
    }
    return false;
}

#endif
