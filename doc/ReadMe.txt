TortoiseHg Documentation

To build this documentation you need sphinx installed.  On Ubuntu this
is the python-sphinx package.   On Windows your best bet is
easy_install.  To build without warnings, you need sphinx 0.6 or later.

To build PDF files you need latex packages.  On Ubuntu this is
texlive-latex-extra and all of it's dependencies.  On Windows the best
choice is miktex.

Once all of the prerequisites are in place, you can use the makefile to
build targets: html htmlhelp latex

Once latex is built, you have to cd into that output directory and run
make all-pdf to build the actual PDF file.

Once htmlhelp is built, you have to run the actual help compiler on a
Windows machine.

On Windows, if you have no make tool you can use build.bat. If HTML
compiler and miktex are installed you can directly generate chm
(build chm) and pdf (build pdf).
