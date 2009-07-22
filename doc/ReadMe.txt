TortoiseHg Documentation

To build this documentation you need sphinx installed.  On Ubuntu this
is the python-sphinx package.   On Windows your best bet is
easy_install.

To build PDF files you need the texlive packages.  On Ubuntu this is
texlive-latex-extra and all of it's dependencies.

On Windows, you also need a make tool.  MinGW of GnuWin32 are
recommended.

Once all of the prerequisites are in place, you use the makefile to
build targets: html htmlhelp latex

Once latex is built, you have to cd into that output directory and run
make all-pdf to build the actual PDF file.

Once htmlhelp is built, you have to run the actual help compiler on a
Windows machine.
