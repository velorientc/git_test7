::
:: Win32 batch file for running the TortoiseHg hgtk script.
:: Copy this file into the install directory and rename hgtk.exe
:: to e.g. hgtk-hidden.exe
::

@echo off
setlocal

:: Uncomment the line below and modify accoringly
::set hgtkpath="C:\path\to\hgtk"
if not defined hgtkpath goto :notfound
python %hgtkpath% %*
goto end

:notfound
echo hgtk: Please configure hgtkpath in %~f0
:end
