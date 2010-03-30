@echo off
hg parents --template "#define THG_PARENT_ID {node|short}\n" > parentid.h
