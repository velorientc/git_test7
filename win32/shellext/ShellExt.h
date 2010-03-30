#ifndef _SHELL_EXT_H_
#define _SHELL_EXT_H_


class CShellExt
{
public:
    static LPCRITICAL_SECTION GetCriticalSection();
    static void IncDllRef();
    static void DecDllRef();
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
