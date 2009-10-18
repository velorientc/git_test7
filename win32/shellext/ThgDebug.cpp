
// Copyright (C) 2009 Adrian Buehlmann
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 2 of the License, or
// (at your option) any later version.

#include "ThgDebug.h"
#include "TortoiseUtils.h"

#include <string>

bool ThgDebug::regDebugShellExt()
{
    std::string val;
    return GetRegistryConfig("DebugShellExt", val) != 0 && val == "1";
}

bool ThgDebug::enabled()
{
    static bool e = regDebugShellExt();
    return e;
}
