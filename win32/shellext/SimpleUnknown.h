// Copyright (C) 2011 Fog Creek Software
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 2 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.

#ifndef _SIMPLEUNKNOWN_H_
#define _SIMPLEUNKNOWN_H_

#define DECLARE_UNKNOWN() \
    STDMETHOD(QueryInterface)(REFIID riid, LPVOID FAR* ppv); \
    STDMETHOD_(ULONG, AddRef)(); \
    STDMETHOD_(ULONG, Release)(); \

#define IMPLEMENT_UNKNOWN(classname) \
    STDMETHODIMP classname::QueryInterface(REFIID riid, LPVOID FAR* ppv) \
    { \
        return CSimpleUnknown::QueryInterface(riid, ppv); \
    } \
    STDMETHODIMP_(ULONG) classname::AddRef() \
    { \
        return CSimpleUnknown::AddRef(); \
    } \
    STDMETHODIMP_(ULONG) classname::Release() \
    { \
        return CSimpleUnknown::Release(); \
    }

#define ADDIFACE(iface) \
    AddInterface(IID_##iface, (iface*)this)

class CSimpleUnknown : public IUnknown
{
    struct Entry
    {
        IID iid;
        LPUNKNOWN punk;
        Entry* next;
    };
    Entry* entries_;
    UINT cRef_;
    
protected:
    void AddInterface(REFIID riid, IUnknown* punk);

public:
    CSimpleUnknown();
    virtual ~CSimpleUnknown();

    DECLARE_UNKNOWN()
};

#endif
