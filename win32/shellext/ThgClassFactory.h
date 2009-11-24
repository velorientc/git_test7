#ifndef _ThgClassFactory_h_
#define _ThgClassFactory_h_

#include "ShellExt.h"


template <class T>
class ThgClassFactory: public IClassFactory
{
    ULONG m_cRef;
    const char myclassToMake;

public:
    explicit ThgClassFactory(char classToMake) :
        myclassToMake(classToMake)
    {
        CShellExt::IncDllRef();
        m_cRef = 0L;
    }


    ~ThgClassFactory()
    {
        CShellExt::DecDllRef();
    }


    STDMETHODIMP QueryInterface(
        REFIID riid, LPVOID FAR* ppv)
    {
        *ppv = NULL;

        if (IsEqualIID(riid, IID_IUnknown) || IsEqualIID(riid, IID_IClassFactory))
        {
            *ppv = (LPCLASSFACTORY) this;
            AddRef();
            return NOERROR;
        }

        return E_NOINTERFACE;
    }


    STDMETHODIMP_(ULONG) AddRef()
    {
        ThgCriticalSection cs(CShellExt::GetCriticalSection());
        return ++m_cRef;
    }


    STDMETHODIMP_(ULONG) Release()
    {
        ThgCriticalSection cs(CShellExt::GetCriticalSection());
        if (--m_cRef)
            return m_cRef;

        delete this;
        return 0L;
    }


    STDMETHODIMP CreateInstance(
        LPUNKNOWN pUnkOuter, REFIID riid, LPVOID* ppvObj)
    {
        *ppvObj = NULL;

        if (pUnkOuter)
            return CLASS_E_NOAGGREGATION;

        T *pShellExt = new T(myclassToMake);
        if (NULL == pShellExt)
            return E_OUTOFMEMORY;

        return pShellExt->QueryInterface(riid, ppvObj);
    }


    STDMETHODIMP LockServer(BOOL fLock)
    {
        return NOERROR;
    }

};


#endif
