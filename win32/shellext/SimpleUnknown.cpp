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

#include "stdafx.h"

#include "SimpleUnknown.h"

CSimpleUnknown::CSimpleUnknown()
  : cRef_(0)
{
    AddInterface(IID_IUnknown, this);
}

CSimpleUnknown::~CSimpleUnknown()
{
}

void CSimpleUnknown::AddInterface(REFIID riid, LPUNKNOWN punk)
{
    Entry e(riid, punk);
    entries_.push_back(e);
}

STDMETHODIMP CSimpleUnknown::QueryInterface(REFIID riid, LPVOID FAR* ppv)
{
    if (ppv == NULL)
        return E_POINTER;

    for (EntriesT::const_iterator i = entries_.begin(); i != entries_.end(); ++i)
    {
        if (i->iid == riid)
        {
            i->punk->AddRef();
            *ppv = i->punk;
            return S_OK;
        }
    }
    *ppv = NULL;
    return E_NOINTERFACE;
}

STDMETHODIMP_(ULONG) CSimpleUnknown::AddRef()
{
    return ::InterlockedIncrement(&cRef_);
}

STDMETHODIMP_(ULONG) CSimpleUnknown::Release()
{
    if (::InterlockedDecrement(&cRef_))
        return cRef_;
    delete this;
    return 0L;
}
