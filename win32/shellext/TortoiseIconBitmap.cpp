#include "stdafx.h"
#include "TortoiseUtils.h"

#include <map>

#include "IconBitmapUtils.h"


HBITMAP GetTortoiseIconBitmap(const std::string& iconname)
{
    IconBitmapUtils bmpUtils;
    typedef std::map<std::string, HBITMAP> BitmapCacheT;
    static BitmapCacheT bmpcache_;

    BitmapCacheT::const_iterator i = bmpcache_.find(iconname);
    if (i != bmpcache_.end())
        return i->second;

    if (bmpcache_.size() > 200)
    {
        TDEBUG_TRACE("**** GetTortoiseIconBitmap: error: too many bitmaps in cache");
        return 0;
    }

    HICON hIcon = GetTortoiseIcon(iconname);
    if (!hIcon)
        return 0;

    HBITMAP hBmp = bmpUtils.IconToBitmapPARGB32(hIcon);
    if (!hBmp)
    {
        TDEBUG_TRACE("**** GetTortoiseIconBitmap: error: something wrong in bmpUtils.ConvertToPARGB32(hIcon)");
        return 0;
    }

    bmpcache_[iconname] = hBmp;

    TDEBUG_TRACE(
        "GetTortoiseIconBitmap: added '" << iconname << "' to bmpcache_"
        " (" << bmpcache_.size() << " bitmaps in cache)"
    );

    return hBmp;
}

