
OBJECTS_DIRSTATE = TortoiseUtils.o \
        Direntry.o \
        Directory.o \
        Winstat.o \
        DirectoryStatus.o

OBJECTS_THGSGELL = $(OBJECTS_DIRSTATE) \
        ContextMenu.o \
        IconOverlay.o \
        MenuActions.o \
        ShellExt.o \
        PipeUtils.o \
        ShellUtils2.o \
        StringUtils.o \
        dirstate.o

BASE_LDFLAGS=-lole32 -lkernel32 -luser32 -lgdi32 -lshlwapi -lwininet \
             -lwinmm -luuid

DEFFILE=ShellExt.def

LDFLAGS_THGSGELL=$(BASE_LDFLAGS) -L/lib \
                 -Wl,--subsystem,windows,--enable-stdcall-fixup,$(DEFFILE) \
                 -mwindows -shared

LDFLAGS_DIRSTATE=$(BASE_LDFLAGS) \
                 -Wl,--subsystem,console,--enable-stdcall-fixup \
                 -mwindows

# set DEBUG env var to 1 to enable debug trace
ifeq ($(DEBUG),1)
CXXFLAGS+=-D_DEBUG
endif

all: THgShell.dll dirstate.exe PipeUtils.exe

THgShell.dll: $(OBJECTS_THGSGELL)
	g++ -o $@ $(OBJECTS_THGSGELL) $(LDFLAGS_THGSGELL)

PipeUtils.exe: PipeUtils.cpp PipeUtils.h StringUtils.o TortoiseUtils.o
	g++ -o $@ $(CXXFLAGS) -DAPPMAIN $< StringUtils.o TortoiseUtils.o

dirstate.exe: dirstate.cpp dirstate.h $(OBJECTS_DIRSTATE)
	g++ -o $@ $(CXXFLAGS) -DAPPMAIN $< $(OBJECTS_DIRSTATE) $(LDFLAGS_DIRSTATE)

clean:
	rm -f *.o *.dll *.exe
