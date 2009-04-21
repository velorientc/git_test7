// CuteHg - Qt4 Dialog Extension of Mercurial
// Copyright (C) 2009 Stefan Rusek 
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

#include <string>
#include <shlwapi.h>


bool HgFindRoot(char* path, std::string* root)
{
	char temp1[MAX_PATH];
	char temp2[MAX_PATH];

	char* dir = temp1;
	char* other = temp2;

	if (!GetFullPathName(path, MAX_PATH, dir, NULL))
		return false;

	bool found = false;
	while (dir)
	{
		other = PathCombine(other, dir, ".\\.hg\\store");
		if (found = PathIsDirectory(other))
			break;

		// search parent
		if (PathIsRoot(dir))
			dir = NULL;
		else
		{
			char* temp = PathCombine(other, dir, "..");
			other = dir;
			dir = temp;
		}
	}

	if (found)
		*root = dir;
	return found;
}

