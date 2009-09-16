[Registry]
; rpc server autostart on logon
Root: HKLM; Subkey: Software\Microsoft\Windows\CurrentVersion\Run; ValueType: string; ValueName: TortoiseHgRpcServer; Flags: uninsdeletevalue; ValueData: {app}\thgtaskbar.exe; Components: shell

; register TortoiseHg config info
Root: HKLM; Subkey: Software\TortoiseHgShell;  Flags: uninsdeletekey; Components: shell
Root: HKLM; Subkey: Software\TortoiseHgShell;  ValueType: string; ValueName: ; ValueData: {app}; Components: shell
Root: HKLM32; Subkey: Software\TortoiseHgShell;  Check: Is64BitInstallMode; Flags: uninsdeletekey; Components: shell
Root: HKLM32; Subkey: Software\TortoiseHgShell;  Check: Is64BitInstallMode; ValueType: string; ValueName: ; ValueData: {app}; Components: shell
Root: HKLM; Subkey: Software\TortoiseHg;  Flags: uninsdeletekey
Root: HKLM; Subkey: Software\TortoiseHg;  ValueType: string; ValueName: ; ValueData: {app}
Root: HKLM32; Subkey: Software\TortoiseHg;  Check: Is64BitInstallMode; Flags: uninsdeletekey
Root: HKLM32; Subkey: Software\TortoiseHg;  Check: Is64BitInstallMode; ValueType: string; ValueName: ; ValueData: {app}

; overlay handler COM controls
;    Normal
Root: HKCR; Subkey: CLSID\{{B456DBA0-7BF4-478c-937A-05130C2C212E}; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA0-7BF4-478c-937A-05130C2C212E}; ValueType: string; ValueName: ; ValueData: TortoiseHg; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA0-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ; ValueData: {app}\THgShell.dll; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA0-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ThreadingModel; ValueData: Apartment; Components: shell
Root: HKCR32; Subkey: CLSID\{{B456DBA0-7BF4-478c-937A-05130C2C212E}; Check: Is64BitInstallMode; Flags: uninsdeletekey; Components: shell
Root: HKCR32; Subkey: CLSID\{{B456DBA0-7BF4-478c-937A-05130C2C212E}; Check: Is64BitInstallMode; ValueType: string; ValueName: ; ValueData: TortoiseHg; Components: shell
Root: HKCR32; Subkey: CLSID\{{B456DBA0-7BF4-478c-937A-05130C2C212E}\InProcServer32; Check: Is64BitInstallMode; ValueType: string; ValueName: ; ValueData: {app}\THgShellx86.dll; Components: shell
Root: HKCR32; Subkey: CLSID\{{B456DBA0-7BF4-478c-937A-05130C2C212E}\InProcServer32; Check: Is64BitInstallMode; ValueType: string; ValueName: ThreadingModel; ValueData: Apartment; Components: shell

;    Added
Root: HKCR; Subkey: CLSID\{{B456DBA1-7BF4-478c-937A-05130C2C212E}; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA1-7BF4-478c-937A-05130C2C212E}; ValueType: string; ValueName: ; ValueData: TortoiseHg; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA1-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ; ValueData: {app}\THgShell.dll; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA1-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ThreadingModel; ValueData: Apartment; Components: shell
Root: HKCR32; Subkey: CLSID\{{B456DBA1-7BF4-478c-937A-05130C2C212E}; Check: Is64BitInstallMode; Flags: uninsdeletekey; Components: shell
Root: HKCR32; Subkey: CLSID\{{B456DBA1-7BF4-478c-937A-05130C2C212E}; Check: Is64BitInstallMode; ValueType: string; ValueName: ; ValueData: TortoiseHg; Components: shell
Root: HKCR32; Subkey: CLSID\{{B456DBA1-7BF4-478c-937A-05130C2C212E}\InProcServer32; Check: Is64BitInstallMode; ValueType: string; ValueName: ; ValueData: {app}\THgShellx86.dll; Components: shell
Root: HKCR32; Subkey: CLSID\{{B456DBA1-7BF4-478c-937A-05130C2C212E}\InProcServer32; Check: Is64BitInstallMode; ValueType: string; ValueName: ThreadingModel; ValueData: Apartment; Components: shell

;   Modified
Root: HKCR; Subkey: CLSID\{{B456DBA2-7BF4-478c-937A-05130C2C212E}; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA2-7BF4-478c-937A-05130C2C212E}; ValueType: string; ValueName: ; ValueData: TortoiseHg; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA2-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ; ValueData: {app}\THgShell.dll; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA2-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ThreadingModel; ValueData: Apartment; Components: shell
Root: HKCR32; Subkey: CLSID\{{B456DBA2-7BF4-478c-937A-05130C2C212E}; Check: Is64BitInstallMode; Flags: uninsdeletekey; Components: shell
Root: HKCR32; Subkey: CLSID\{{B456DBA2-7BF4-478c-937A-05130C2C212E}; Check: Is64BitInstallMode; ValueType: string; ValueName: ; ValueData: TortoiseHg; Components: shell
Root: HKCR32; Subkey: CLSID\{{B456DBA2-7BF4-478c-937A-05130C2C212E}\InProcServer32; Check: Is64BitInstallMode; ValueType: string; ValueName: ; ValueData: {app}\THgShellx86.dll; Components: shell
Root: HKCR32; Subkey: CLSID\{{B456DBA2-7BF4-478c-937A-05130C2C212E}\InProcServer32; Check: Is64BitInstallMode; ValueType: string; ValueName: ThreadingModel; ValueData: Apartment; Components: shell

;   Unversioned
Root: HKCR; Subkey: CLSID\{{B456DBA6-7BF4-478c-937A-05130C2C212E}; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA6-7BF4-478c-937A-05130C2C212E}; ValueType: string; ValueName: ; ValueData: TortoiseHg; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA6-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ; ValueData: {app}\THgShell.dll; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA6-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ThreadingModel; ValueData: Apartment; Components: shell
Root: HKCR32; Subkey: CLSID\{{B456DBA6-7BF4-478c-937A-05130C2C212E}; Check: Is64BitInstallMode; Flags: uninsdeletekey; Components: shell
Root: HKCR32; Subkey: CLSID\{{B456DBA6-7BF4-478c-937A-05130C2C212E}; Check: Is64BitInstallMode; ValueType: string; ValueName: ; ValueData: TortoiseHg; Components: shell
Root: HKCR32; Subkey: CLSID\{{B456DBA6-7BF4-478c-937A-05130C2C212E}\InProcServer32; Check: Is64BitInstallMode; ValueType: string; ValueName: ; ValueData: {app}\THgShellx86.dll; Components: shell
Root: HKCR32; Subkey: CLSID\{{B456DBA6-7BF4-478c-937A-05130C2C212E}\InProcServer32; Check: Is64BitInstallMode; ValueType: string; ValueName: ThreadingModel; ValueData: Apartment; Components: shell

; The actual icon overlay handlers for Explorer
Root: HKLM; Subkey: Software\TortoiseOverlays\Normal; ValueType: string; ValueName: TortoiseHg; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell
Root: HKLM; Subkey: Software\TortoiseOverlays\Added; ValueType: string; ValueName: TortoiseHg; ValueData: {{B456DBA1-7BF4-478c-937A-05130C2C212E}; Components: shell
Root: HKLM; Subkey: Software\TortoiseOverlays\Modified; ValueType: string; ValueName: TortoiseHg; ValueData: {{B456DBA2-7BF4-478c-937A-05130C2C212E}; Components: shell
Root: HKLM; Subkey: Software\TortoiseOverlays\Unversioned; ValueType: string; ValueName: TortoiseHg; ValueData: {{B456DBA6-7BF4-478c-937A-05130C2C212E}; Components: shell
Root: HKLM32; Subkey: Software\TortoiseOverlays\Normal; Check: Is64BitInstallMode; ValueType: string; ValueName: TortoiseHg; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell
Root: HKLM32; Subkey: Software\TortoiseOverlays\Added; Check: Is64BitInstallMode; ValueType: string; ValueName: TortoiseHg; ValueData: {{B456DBA1-7BF4-478c-937A-05130C2C212E}; Components: shell
Root: HKLM32; Subkey: Software\TortoiseOverlays\Modified; Check: Is64BitInstallMode; ValueType: string; ValueName: TortoiseHg; ValueData: {{B456DBA2-7BF4-478c-937A-05130C2C212E}; Components: shell
Root: HKLM32; Subkey: Software\TortoiseOverlays\Unversioned; Check: Is64BitInstallMode; ValueType: string; ValueName: TortoiseHg; ValueData: {{B456DBA6-7BF4-478c-937A-05130C2C212E}; Components: shell

; Make them approved by administrator
Root: HKLM; Subkey: SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved; ValueType: string; ValueName: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; ValueData: TortoiseHg; Flags: uninsdeletevalue; Components: shell
Root: HKLM; Subkey: SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved; ValueType: string; ValueName: {{B456DBA1-7BF4-478c-937A-05130C2C212E}; ValueData: TortoiseHg; Flags: uninsdeletevalue; Components: shell
Root: HKLM; Subkey: SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved; ValueType: string; ValueName: {{B456DBA2-7BF4-478c-937A-05130C2C212E}; ValueData: TortoiseHg; Flags: uninsdeletevalue; Components: shell
Root: HKLM; Subkey: SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved; ValueType: string; ValueName: {{B456DBA6-7BF4-478c-937A-05130C2C212E}; ValueData: TortoiseHg; Flags: uninsdeletevalue; Components: shell
Root: HKLM32; Subkey: SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved; Check: Is64BitInstallMode; ValueType: string; ValueName: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; ValueData: TortoiseHg; Flags: uninsdeletevalue; Components: shell
Root: HKLM32; Subkey: SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved; Check: Is64BitInstallMode; ValueType: string; ValueName: {{B456DBA1-7BF4-478c-937A-05130C2C212E}; ValueData: TortoiseHg; Flags: uninsdeletevalue; Components: shell
Root: HKLM32; Subkey: SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved; Check: Is64BitInstallMode; ValueType: string; ValueName: {{B456DBA2-7BF4-478c-937A-05130C2C212E}; ValueData: TortoiseHg; Flags: uninsdeletevalue; Components: shell
Root: HKLM32; Subkey: SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved; Check: Is64BitInstallMode; ValueType: string; ValueName: {{B456DBA6-7BF4-478c-937A-05130C2C212E}; ValueData: TortoiseHg; Flags: uninsdeletevalue; Components: shell

; Context menu handlers
Root: HKCR; Subkey: Directory\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: Directory\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell
Root: HKCR32; Subkey: Directory\shellex\ContextMenuHandlers\TortoiseHgCMenu; Check: Is64BitInstallMode; Flags: uninsdeletekey; Components: shell
Root: HKCR32; Subkey: Directory\shellex\ContextMenuHandlers\TortoiseHgCMenu; Check: Is64BitInstallMode; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell

Root: HKCR; Subkey: Directory\Background\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: Directory\Background\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell
Root: HKCR32; Subkey: Directory\Background\shellex\ContextMenuHandlers\TortoiseHgCMenu; Check: Is64BitInstallMode; Flags: uninsdeletekey; Components: shell
Root: HKCR32; Subkey: Directory\Background\shellex\ContextMenuHandlers\TortoiseHgCMenu; Check: Is64BitInstallMode; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell

Root: HKCR; Subkey: Drive\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: Drive\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell
Root: HKCR32; Subkey: Drive\shellex\ContextMenuHandlers\TortoiseHgCMenu; Check: Is64BitInstallMode; Flags: uninsdeletekey; Components: shell
Root: HKCR32; Subkey: Drive\shellex\ContextMenuHandlers\TortoiseHgCMenu; Check: Is64BitInstallMode; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell

Root: HKCR; Subkey: Folder\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: Folder\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell
Root: HKCR32; Subkey: Folder\shellex\ContextMenuHandlers\TortoiseHgCMenu; Check: Is64BitInstallMode; Flags: uninsdeletekey; Components: shell
Root: HKCR32; Subkey: Folder\shellex\ContextMenuHandlers\TortoiseHgCMenu; Check: Is64BitInstallMode; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell

Root: HKCR; Subkey: *\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: *\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell
Root: HKCR32; Subkey: *\shellex\ContextMenuHandlers\TortoiseHgCMenu; Check: Is64BitInstallMode; Flags: uninsdeletekey; Components: shell
Root: HKCR32; Subkey: *\shellex\ContextMenuHandlers\TortoiseHgCMenu; Check: Is64BitInstallMode; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell

Root: HKCR; Subkey: InternetShortcut\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: InternetShortcut\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell
Root: HKCR32; Subkey: InternetShortcut\shellex\ContextMenuHandlers\TortoiseHgCMenu; Check: Is64BitInstallMode; Flags: uninsdeletekey; Components: shell
Root: HKCR32; Subkey: InternetShortcut\shellex\ContextMenuHandlers\TortoiseHgCMenu; Check: Is64BitInstallMode; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell

