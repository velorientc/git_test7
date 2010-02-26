:: %1 - TortoiseHg Version first level
:: %2 - second level
:: %3 - third level
:: %4 - platform (x86 or x64)
:: %5 - msi product id (GUID)

set _SDKBIN_=%PROGRAMFILES%\Microsoft SDKs\Windows\v7.0\Bin
if exist "%_SDKBIN_%" goto :ok
set _SDKBIN_=%ProgramW6432%\Microsoft SDKs\Windows\v7.0\Bin
if exist "%_SDKBIN_%" goto :ok
echo Microsoft Windows SDK 7 SP1 not installed
pause
exit 1
:ok

cd win32\shellext

call "%_SDKBIN_%\SetEnv.cmd" /xp /%4 /release
set DEBUG=1
set THG_PLATFORM=%4
set THG_EXTRA_CPPFLAGS=/DTHG_MSI_INSTALL /DTHG_PRODUCT_ID=%5
set THG_EXTRA_RCFLAGS=/dTHG_VERSION_FIRST=%1 /dTHG_VERSION_SECOND=%2 /dTHG_VERSION_THIRD=%3 /dTHG_PRODUCT_ID="%5"
nmake /f Makefile.nmake clean
nmake /f Makefile.nmake
move ThgShell%4.dll ..
move terminate-%4.exe ..
