#ifndef _ThgClassFactory_h_
#define _ThgClassFactory_h_

#include "ShellExt.h"
#include "SimpleUnknown.h"

template <class T>
class ThgClassFactory: public CSimpleUnknown, public IClassFactory
{
    const char myclassToMake;

public:
    explicit ThgClassFactory(char classToMake) :
        myclassToMake(classToMake)
    {
        CShellExt::IncDllRef();
        ADDIFACE(IClassFactory);
    }


    ~ThgClassFactory()
    {
        CShellExt::DecDllRef();
    }

    INLINE_UNKNOWN()

    STDMETHODIMP CreateInstance(
        LPUNKNOWN pUnkOuter, REFIID riid, LPVOID* ppvObj)
    {
        if (ppvObj == 0)
            return E_POINTER;

        *ppvObj = NULL;

        if (pUnkOuter)
            return CLASS_E_NOAGGREGATION;

        T *pShellExt = new T(myclassToMake);
        if (NULL == pShellExt)
            return E_OUTOFMEMORY;

        const HRESULT hr = pShellExt->QueryInterface(riid, ppvObj);
        if (FAILED(hr))
            delete pShellExt;

        return hr;
    }


    STDMETHODIMP LockServer(BOOL fLock)
    {
        return S_OK;
    }

};


#endif
