#ifndef _SHELL_EXT_H_
#define _SHELL_EXT_H_


class CShellExt
{
    static CRITICAL_SECTION cs_;
    static HMODULE hModule_;
    static UINT cRef_;

public:
    static LPCRITICAL_SECTION GetCriticalSection() { return &cs_; }
    static UINT GetRefCount() { return cRef_; }
    static void IncDllRef() { ::InterlockedIncrement(&cRef_); }
    static void DecDllRef() { ::InterlockedDecrement(&cRef_); }

    friend BOOL WINAPI DllMain(HINSTANCE, DWORD, LPVOID);
};


class ThgCriticalSection
{
    LPCRITICAL_SECTION cs_;

public:
    ThgCriticalSection(LPCRITICAL_SECTION cs): cs_(cs)
    {
        ::EnterCriticalSection(cs_);
    }

    ~ThgCriticalSection()
    {
        ::LeaveCriticalSection(cs_);
    }
};


#endif // _SHELL_EXT_H_
