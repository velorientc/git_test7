DLLNAME=THgShell.dll

OBJECTS = ContextMenu.o \
        IconOverlay.o \
        MenuActions.o \
        ShellExt.o \
        TortoiseUtils.o \
        PipeUtils.o \
        ShellUtils2.o \
        StringUtils.o \
        Direntry.o \
        Directory.o \
        dirstate.o

DEFFILE=ShellExt.def

LDFLAGS=-L/lib -lole32 -lkernel32 -luser32 -lgdi32 -lshlwapi \
        -lwininet -lwinmm -luuid \
        -Wl,--subsystem,windows,--enable-stdcall-fixup,$(DEFFILE) \
        -mwindows -shared

# set DEBUG env var to 1 to enable debug trace
ifeq ($(DEBUG),1)
CXXFLAGS+=-D_DEBUG
endif

all: PipeUtils $(DLLNAME)
	
$(DLLNAME): $(OBJECTS)
	g++ -o $@ $(OBJECTS) $(LDFLAGS)

PipeUtils: PipeUtils.cpp PipeUtils.h StringUtils.o TortoiseUtils.o
	g++ -o $@ $(CXXFLAGS) -DAPPMAIN $< StringUtils.o TortoiseUtils.o

clean:
	rm -f *.o *.dll *.exe
