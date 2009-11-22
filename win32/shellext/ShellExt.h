#ifndef _SHELL_EXT_H_
#define _SHELL_EXT_H_


class CShellExt
{
public:
    static LPCRITICAL_SECTION GetCriticalSection();
    static void IncDllRef();
    static void DecDllRef();
};


class CShellExtOverlay: public IShellIconOverlayIdentifier
{
    ULONG m_cRef;
    const char myTortoiseClass;

public:
    explicit CShellExtOverlay(char Class);
    ~CShellExtOverlay();

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, LPVOID FAR *ppv);
    STDMETHODIMP_(ULONG) AddRef();
    STDMETHODIMP_(ULONG) Release();

    // IShellIconOverlayIdentifier
    STDMETHODIMP GetOverlayInfo(
        LPWSTR pwszIconFile, int cchMax, int* pIndex, DWORD* pdwFlags);
    STDMETHODIMP GetPriority(int* pPriority);
    STDMETHODIMP IsMemberOf(LPCWSTR pwszPath, DWORD dwAttrib);
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
