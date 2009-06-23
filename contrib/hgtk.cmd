::
:: Win32 batch file for running the TortoiseHg hgtk script.
::

@echo off
setlocal

:: Uncomment the line below and modify accoringly
::set hgtkpath="C:\repos\tortoisehg-crew\hgtk"
if not exist %hgtkpath% goto :notfound
python %hgtkpath% %*
goto end

:notfound
echo hgtk: Please configure kgtkpath in %~f0
:end
