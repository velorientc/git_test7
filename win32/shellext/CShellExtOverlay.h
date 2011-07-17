#ifndef _CShellExtOverlay_h_
#define _CShellExtOverlay_h_

#include "SimpleUnknown.h"

class CShellExtOverlay: public CSimpleUnknown, public IShellIconOverlayIdentifier
{
    const char myTortoiseClass;

public:
    explicit CShellExtOverlay(char Class);
    ~CShellExtOverlay();

    DECLARE_UNKNOWN()

    // IShellIconOverlayIdentifier
    STDMETHODIMP GetOverlayInfo(
        LPWSTR pwszIconFile, int cchMax, int* pIndex, DWORD* pdwFlags);
    STDMETHODIMP GetPriority(int* pPriority);
    STDMETHODIMP IsMemberOf(LPCWSTR pwszPath, DWORD dwAttrib);
};


#endif
