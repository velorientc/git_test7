// Copyright (C) 2002 - Francis Irving
// <francis@flourish.org> - May 2002

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

#ifndef _STRING_UTILS_H
#define _STRING_UTILS_H

#include <string>
#include <windows.h>

// Quotes a string
std::string Quote(const std::string& str);

// Convert Unicode string to multibyte string
std::string WideToMultibyte(const std::wstring& wide, UINT CodePage = CP_ACP);

// Convert multibyte string to Unicode string
std::wstring MultibyteToWide(const std::string& multibyte, UINT CodePage = CP_ACP);


#endif