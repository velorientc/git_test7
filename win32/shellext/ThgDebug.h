
// Copyright (C) 2009 Adrian Buehlmann
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 2 of the License, or
// (at your option) any later version.

#ifndef THGDEBUG_H
#define THGDEBUG_H

class ThgDebug
{
public:
    static bool enabled();

private:
    ThgDebug();
    
    static bool regDebugShellExt();
};

#endif
