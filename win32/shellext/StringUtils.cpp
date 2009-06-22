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
// Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

#include "StringUtils.h"


// Quotes a string
std::string Quote(const std::string& str)
{
   std::string sResult = "\"" + str + "\"";
   return sResult;
}


// Convert Unicode string to multibyte string
std::string WideToMultibyte(const std::wstring& wide, UINT CodePage)
{
    char* narrow = NULL;
    // Determine length of string
    int ret = WideCharToMultiByte(
        CodePage, 0, wide.c_str(), static_cast<int>(wide.length()),
        NULL, 0, NULL, NULL
    );
    narrow = new char[ret + 1];
    std::auto_ptr<char> free_narrow(narrow);
    ret = WideCharToMultiByte(
        CodePage, 0, wide.c_str(), static_cast<int>(wide.length()),
        narrow, ret, NULL, NULL
    );
    narrow[ret] = '\0';
    return narrow;
}


// Convert multibyte string to Unicode string 
std::wstring MultibyteToWide(const std::string& multibyte, UINT CodePage)
{
    wchar_t* wide = NULL;
    int ret = MultiByteToWideChar(
        CodePage, 0, multibyte.c_str(), 
        static_cast<int>(multibyte.length()), 0, 0
    );
    wide = new wchar_t[ret + 1];
    std::auto_ptr<wchar_t> free_narrow(wide);
    ret = MultiByteToWideChar(
        CodePage, 0, multibyte.c_str(),
        static_cast<int>(multibyte.length()), wide, ret);
    wide[ret] = L'\0';
    return wide;
}
