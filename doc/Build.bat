@echo off

set hhc_compiler="%ProgramFiles%\HTML Help Workshop\hhc.exe"
set PDFLATEX=PdfLatex
set OUTPUTDIR=build
set SPHINXBUILD=sphinx-build
set ALLSPHINXOPTS=-d %OUTPUTDIR%/doctrees %SPHINXOPTS% source
if NOT "%PAPER%" == "" (
	set ALLSPHINXOPTS=-D latex_paper_size=%PAPER% %ALLSPHINXOPTS%
)

if "%1" == "" goto help

if "%1" == "help" (
	:help
	echo.Please use `make ^<target^>` where ^<target^> is one of
	echo.  html      to make standalone HTML files
	echo.  htmlhelp  to make HTML files and a HTML help project
	echo.  chm       to make CHM file
	echo.  latex     to make LaTeX files, you can set PAPER=a4 or PAPER=letter
	echo.  pdf       to make PDF file, you can set PAPER=a4 or PAPER=letter
	goto end
)

if "%1" == "clean" (
	for /d %%i in (%OUTPUTDIR%\*) do rmdir /q /s %%i
	del /q /s %OUTPUTDIR%\*
	goto end
)

if "%1" == "html" (
	%SPHINXBUILD% -b html %ALLSPHINXOPTS% %OUTPUTDIR%/html
	echo.
	echo.Build finished. The HTML pages are in %OUTPUTDIR%/html.
	goto end
)

if "%1" == "htmlhelp" (
	%SPHINXBUILD% -b htmlhelp %ALLSPHINXOPTS% %OUTPUTDIR%/htmlhelp
	echo.
	echo.Build finished; now you can run HTML Help Workshop with the ^
.hhp project file in %OUTPUTDIR%/htmlhelp.
	goto end
)

if "%1" == "chm" (
	%SPHINXBUILD% -b htmlhelp %ALLSPHINXOPTS% %OUTPUTDIR%/chm
	%hhc_compiler% %OUTPUTDIR%/chm/TortoiseHGdoc.hhp
	echo.
	echo.Build finished. The CHM file is in %OUTPUTDIR%/chm.
	goto end
)

if "%1" == "latex" (
	%SPHINXBUILD% -b latex %ALLSPHINXOPTS% %OUTPUTDIR%/latex
	echo.
	echo.Build finished; the LaTeX files are in %OUTPUTDIR%/latex.
	goto end
)

if "%1" == "pdf" (
	%SPHINXBUILD% -b latex %ALLSPHINXOPTS% %OUTPUTDIR%/pdf
	pushd .
	cd %OUTPUTDIR%\pdf
	%PDFLATEX% TortoiseHG.tex
	popd
	echo.
	echo.Build finished; the PDF file is in %OUTPUTDIR%/pdf.
	goto end
)

:end



