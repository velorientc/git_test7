@echo off

:: calls hg thgstatus for all directories in current dir
 
for /F "tokens=*" %%G in ('dir /b /A:D') do (
  echo %%G
  hg -R %%G thgstatus)
