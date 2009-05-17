::
:: Win32 batch file for running the TortoiseHg hgtk script.
::

@echo off
setlocal

:: Uncomment the line below and modify accoringly
:: set TortoisePath = C:\repos\thg-stable
if "%TortoisePath%"=="" (goto :notfound)

:hgproc
python "%TortoisePath%\hgtk" %*
goto end

:notfound
echo hgtk: Please configure TortoiseHg location in %~f0

:end
