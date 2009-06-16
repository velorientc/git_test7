
OBJECTS_DIRSTATE = TortoiseUtils.o \
        Direntry.o \
        Directory.o \
        Winstat.o

OBJECTS_THGSGELL = $(OBJECTS_DIRSTATE) \
        ContextMenu.o \
        IconOverlay.o \
        ShellExt.o \
        ShellUtils2.o \
        StringUtils.o \
        dirstate.o \
        Winstat64.o \
        Dirstatecache.o \
        DirectoryStatus.o \
        Thgstatus.o \
        QueryDirstate.o

BASE_LDFLAGS=-lole32 -lshlwapi -luuid

DEFFILE=ShellExt.def

LDFLAGS_THGSGELL=$(BASE_LDFLAGS) -L/lib \
                 -Wl,--subsystem,windows,--enable-stdcall-fixup,$(DEFFILE) \
                 -mwindows -shared

LDFLAGS_DIRSTATE=$(BASE_LDFLAGS) \
                 -Wl,--subsystem,console,--enable-stdcall-fixup \
                 -mwindows

# set DEBUG env var to 1 to enable debug trace
ifeq ($(DEBUG),1)
CXXFLAGS+=-DTHG_DEBUG
endif

all: THgShell.dll dirstate.exe

THgShell.dll: $(OBJECTS_THGSGELL)
	g++ -o $@ $(OBJECTS_THGSGELL) -s $(LDFLAGS_THGSGELL)

dirstate.exe: dirstate.cpp dirstate.h $(OBJECTS_DIRSTATE)
	g++ -o $@ $(CXXFLAGS) -DAPPMAIN $< $(OBJECTS_DIRSTATE) $(LDFLAGS_DIRSTATE)

clean:
	rm -f *.o *.dll *.exe
