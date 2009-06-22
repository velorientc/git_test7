// TortoiseCVS - a Windows shell extension for easy version control

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
// Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

#ifndef _STRING_UTILS_H
#define _STRING_UTILS_H

#include <string>
#include <vector>
#include <windows.h>


// From: http://www.kbcafe.com/articles/cplusplus.tricks.html
template<class T> void FindAndReplace(T& source, const T& find, const T& replace)
{
   size_t j;
   for (j = 0; (j = source.find(find, j)) != T::npos;)
   {
      source.replace(j, find.length(), replace);
      j += replace.length();
   }
}

// Return the length of the longest string in the vector.
int MaxStringLength(const std::vector<std::string>& stringvec);

// Remove leading whitespaces from a string
std::string TrimLeft(const std::string& str);


// Remove trailing whitespaces from a string
std::string TrimRight(const std::string& str);


// Remove leading and trailing whitespaces from a string
std::string Trim(const std::string& str);

// Test if string starts with substr
bool StartsWith(const std::string& str, const std::string& substr);

// Quotes a string
std::string Quote(const std::string& str);

// Cuts the first token off a delimited list
std::string CutFirstToken(std::string& sList, const std::string sDelimiter);

// Convert Unicode string to multibyte string
std::string WideToMultibyte(const std::wstring& wide, UINT CodePage = CP_ACP);

// Convert multibyte string to Unicode string 
std::wstring MultibyteToWide(const std::string& multibyte, UINT CodePage = CP_ACP);

// Serialize a vector of strings
std::string SerializeStringVector(const std::vector<std::string>& vStrings, 
                                  const std::string& sDelimiter);

// comparison function object
class less_nocase 
{
public:
   bool operator()(const std::string& x, const std::string& y) const
   {
      std::string::const_iterator p = x.begin();
      std::string::const_iterator q = y.begin();

      while (p != x.end() && q != y.end() && toupper(*p) == toupper(*q))
         ++p, ++q;

      if (p == x.end())         // Reached end of x: Return true if y is longer than x
         return q != y.end();

      if (q == y.end())         // Reached end of y, but not x, so x is longer than y
         return false;

      return toupper(*p) < toupper(*q);
   }
};


#endif
