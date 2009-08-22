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

#define ASSERT assert


#ifdef THG_DEBUG
    #include <sstream>

    // TDEBUG_TRACE() prints debugging messages to Windows' debugger display.
    // The messages can be viewed with Sysinternals DebugView, which may be
    // downloaded from Microsoft TechNet.
    #define TDEBUG_TRACE(s) do {                                            \
                               std::stringstream _the_msg;                  \
                               _the_msg << "[THG] " << s;                   \
                               std::string _the_str = _the_msg.str();       \
                               OutputDebugStringA(_the_str.c_str());         \
                            } while (0)
    #define TDEBUG_TRACEW(s) do {                                            \
                               std::basic_stringstream<wchar_t> _the_msg;    \
                               _the_msg << L"[THG] " << s;                   \
                               std::wstring _the_str = _the_msg.str();       \
                               OutputDebugStringW(_the_str.c_str());         \
                            } while (0)
    #define TDEBUG_ENTER TDEBUG_TRACE
#else
    #define TDEBUG_TRACE(s)
    #define TDEBUG_ENTER(s)

#endif

#endif

