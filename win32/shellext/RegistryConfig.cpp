#include "stdafx.h"
#include "RegistryConfig.h"

int GetRegistryConfig(const std::string& name, std::string& res)
{
    const char* const subkey = "Software\\TortoiseHg";

    HKEY hkey = 0;
    LONG rv = RegOpenKeyExA(
        HKEY_CURRENT_USER, subkey, 0, KEY_READ, &hkey);

    if (rv != ERROR_SUCCESS || hkey == 0)
        return 0;

    BYTE Data[MAX_PATH] = "";
    DWORD cbData = MAX_PATH * sizeof(BYTE);

    rv = RegQueryValueExA(
        hkey, name.c_str(), 0, 0, Data, &cbData);

    int ret = 0;
    if (rv == ERROR_SUCCESS)
    {
        res = reinterpret_cast<const char*>(&Data);
        ret = 1;
    }

    RegCloseKey(hkey);
    return ret;
}
