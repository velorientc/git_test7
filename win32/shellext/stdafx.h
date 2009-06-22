#ifndef _STDAFX_H_
#define _STDAFX_H_

/*
 Per MingW's winder.h:
 * If you need Win32 API features newer the Win95 and WinNT then you must
 * define WINVER before including windows.h or any other method of including
 * the windef.h header.
 */
#define WINVER 0x0500   // need to enable  hbmpItem member in MENUITEMINFO

#include <windows.h>
#include <windowsx.h>
#include <shlobj.h>
#include <assert.h>
#include <string>
#include <map>

#define ASSERT assert

#define WindowsVersionIsNT4() (0)

#define ResultFromShort(i)  ResultFromScode(MAKE_SCODE(SEVERITY_SUCCESS, 0, (USHORT)(i)))

#ifdef THG_DEBUG
    #include <sstream>

    // TDEBUG_TRACE() prints debugging messages to Windows' debugger display.
    // The messages can be viewed with Sysinternals DebugView, which may be
    // downloaded from Microsoft TechNet.
    #define TDEBUG_TRACE(s) do {                                            \
                               std::stringstream _the_msg;                  \
                               _the_msg << "[THG] " << s;                   \
                               std::string _the_str = _the_msg.str();       \
                               OutputDebugString(_the_str.c_str());         \
                            } while (0)
    #define TDEBUG_ENTER TDEBUG_TRACE
#else
    #define TDEBUG_TRACE(s)
    #define TDEBUG_ENTER(s)

#endif

#endif

