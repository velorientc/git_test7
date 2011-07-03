// Copyright (C) 2002 - Torsten Martinsen
// <torsten@tiscali.dk> - September 2002

// This program is free software; you can redistribute it and/or
// modify it under the terms of the GNU General Public License
// as published by the Free Software Foundation; either version 2
// of the License, or (at your option) any later version.

// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.

// You should have received a copy of the GNU General Public License
// along with this program; if not, write to the Free Software
// Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

#include "StringUtils.h"

#include <vector>


// Quotes a string
std::string Quote(const std::string& str)
{
   std::string sResult = "\"" + str + "\"";
   return sResult;
}


// Convert Unicode string to multibyte string
std::string WideToMultibyte(const std::wstring& wide, UINT CodePage)
{
    // Determine length of string
    int ret = WideCharToMultiByte(
        CodePage, 0, wide.c_str(), static_cast<int>(wide.length()),
        NULL, 0, NULL, NULL
    );

    std::vector<CHAR> narrow(ret + 1);

    ret = WideCharToMultiByte(
        CodePage, 0, wide.c_str(), static_cast<int>(wide.length()),
        &narrow[0], ret, NULL, NULL
    );
    narrow[ret] = '\0';

    return &narrow[0];
}


// Convert multibyte string to Unicode string
std::wstring MultibyteToWide(const std::string& multibyte, UINT CodePage)
{
    int ret = MultiByteToWideChar(
        CodePage, 0, multibyte.c_str(),
        static_cast<int>(multibyte.length()), 0, 0
    );

    std::vector<wchar_t> wide(ret + 1);

    ret = MultiByteToWideChar(
        CodePage, 0, multibyte.c_str(),
        static_cast<int>(multibyte.length()), &wide[0], ret
    );
    wide[ret] = L'\0';

    return &wide[0];
}
