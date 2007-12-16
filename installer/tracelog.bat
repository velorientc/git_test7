@echo off
rem ="""
python -x %~f0 %*
exit 0
"""
# -------------------- Python section --------------------
from hggtk import tracelog
tracelog.run()
