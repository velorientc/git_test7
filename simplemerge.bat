::
:: Win32 batch file to handle to merge with simplemerge for developement of TortoiseHg
::

@echo off
setlocal

:: Look in the registry for TortoiseHg location
for /f "skip=2 tokens=3*" %%A in (
    '"reg query "HKEY_LOCAL_MACHINE\SOFTWARE\TortoiseHg" /ve 2> nul"' ) do set TortoisePath=%%B
if "%TortoisePath%"=="" (goto :notfound) else (goto :merge)

:merge
python "%TortoisePath%\hgutils\simplemerge" %*
goto end

:notfound
echo hgproc: cannot find TortoiseHg location in the registry.

:end
