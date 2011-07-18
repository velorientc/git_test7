#ifndef _CShellExtDnd_h_
#define _CShellExtDnd_h_

#include "CShellExtCMenu.h"


//CShellExtCMenu implements IContextMenu3, IShellExtInit
class CShellExtDnd: public CShellExtCMenu
{

protected:
    virtual void RunDialog(const std::string&);

public:
    explicit CShellExtDnd(const char dummy);
    ~CShellExtDnd();

    // IContextMenu3
    STDMETHOD(QueryContextMenu)(
        HMENU hMenu, UINT indexMenu, UINT idCmdFirst, UINT idCmdLast,
        UINT uFlags);

    // IShellExtInit
    STDMETHOD(Initialize)(
        LPCITEMIDLIST pIDFolder, LPDATAOBJECT pDataObj, HKEY hKeyID);
};


#endif
