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
{
    entries_ = NULL;
    cRef_ = 0;
    AddInterface(IID_IUnknown, this);
}

CSimpleUnknown::~CSimpleUnknown()
{
    Entry* entry = entries_;
    while (entry != NULL)
    {
        Entry* nextentry = entry->next;
        delete entry;
        entry = nextentry;
    }
}

void CSimpleUnknown::AddInterface(REFIID riid, LPUNKNOWN punk)
{
    Entry* newentry = new Entry;
    newentry->iid = riid;
    newentry->punk = punk;
    newentry->next = entries_;
    entries_ = newentry;
}

STDMETHODIMP CSimpleUnknown::QueryInterface(REFIID riid, LPVOID FAR* ppv)
{
    if (ppv == NULL)
        return E_POINTER;

    for (Entry* entry = entries_; entry != NULL; entry = entry->next)
    {
        if (entry->iid == riid)
        {
            entry->punk->AddRef();
            *ppv = entry->punk;
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
