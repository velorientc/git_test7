@echo off

:: calls hgtk thgstatus for all directories in current dir

for /F "tokens=*" %%G in ('dir /b /A:D') do (
  echo updating %%G
  call hgtk -R %%G thgstatus --notify %%G)
