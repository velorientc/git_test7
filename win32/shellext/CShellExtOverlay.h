#ifndef _CShellExtOverlay_h_
#define _CShellExtOverlay_h_


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


#endif
