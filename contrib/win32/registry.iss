[Registry]
; rpc server autostart on logon
Root: HKLM; Subkey: Software\Microsoft\Windows\CurrentVersion\Run; ValueType: string; ValueName: TortoiseHgRpcServer; Flags: uninsdeletevalue; ValueData: {app}\thgtaskbar.exe; Components: shell

; register TortoiseHg config info
Root: HKLM; Subkey: Software\TortoiseHgShell;  Flags: uninsdeletekey; Components: shell
Root: HKLM; Subkey: Software\TortoiseHgShell;  ValueType: string; ValueName: ; ValueData: {app}; Components: shell
Root: HKLM; Subkey: Software\TortoiseHg;  Flags: uninsdeletekey
Root: HKLM; Subkey: Software\TortoiseHg;  ValueType: string; ValueName: ; ValueData: {app}

; overlay handler COM controls
;    Normal
Root: HKCR; Subkey: CLSID\{{B456DBA0-7BF4-478c-937A-05130C2C212E}; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA0-7BF4-478c-937A-05130C2C212E}; ValueType: string; ValueName: ; ValueData: TortoiseHg; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA0-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ; ValueData: {app}\THgShell.dll; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA0-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ThreadingModel; ValueData: Apartment; Components: shell

;    Added
Root: HKCR; Subkey: CLSID\{{B456DBA1-7BF4-478c-937A-05130C2C212E}; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA1-7BF4-478c-937A-05130C2C212E}; ValueType: string; ValueName: ; ValueData: TortoiseHg; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA1-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ; ValueData: {app}\THgShell.dll; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA1-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ThreadingModel; ValueData: Apartment; Components: shell

;   Modified
Root: HKCR; Subkey: CLSID\{{B456DBA2-7BF4-478c-937A-05130C2C212E}; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA2-7BF4-478c-937A-05130C2C212E}; ValueType: string; ValueName: ; ValueData: TortoiseHg; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA2-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ; ValueData: {app}\THgShell.dll; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA2-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ThreadingModel; ValueData: Apartment; Components: shell

;   Unversioned
Root: HKCR; Subkey: CLSID\{{B456DBA6-7BF4-478c-937A-05130C2C212E}; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA6-7BF4-478c-937A-05130C2C212E}; ValueType: string; ValueName: ; ValueData: TortoiseHg; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA6-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ; ValueData: {app}\THgShell.dll; Components: shell
Root: HKCR; Subkey: CLSID\{{B456DBA6-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ThreadingModel; ValueData: Apartment; Components: shell

; The actual icon overlay handlers for Explorer
Root: HKLM; Subkey: Software\TortoiseOverlays\Normal; ValueType: string; ValueName: TortoiseHg; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell
Root: HKLM; Subkey: Software\TortoiseOverlays\Added; ValueType: string; ValueName: TortoiseHg; ValueData: {{B456DBA1-7BF4-478c-937A-05130C2C212E}; Components: shell
Root: HKLM; Subkey: Software\TortoiseOverlays\Modified; ValueType: string; ValueName: TortoiseHg; ValueData: {{B456DBA2-7BF4-478c-937A-05130C2C212E}; Components: shell
Root: HKLM; Subkey: Software\TortoiseOverlays\Unversioned; ValueType: string; ValueName: TortoiseHg; ValueData: {{B456DBA6-7BF4-478c-937A-05130C2C212E}; Components: shell

; Make them approved by administrator
Root: HKLM; Subkey: SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved; ValueType: string; ValueName: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; ValueData: TortoiseHg; Flags: uninsdeletevalue; Components: shell
Root: HKLM; Subkey: SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved; ValueType: string; ValueName: {{B456DBA1-7BF4-478c-937A-05130C2C212E}; ValueData: TortoiseHg; Flags: uninsdeletevalue; Components: shell
Root: HKLM; Subkey: SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved; ValueType: string; ValueName: {{B456DBA2-7BF4-478c-937A-05130C2C212E}; ValueData: TortoiseHg; Flags: uninsdeletevalue; Components: shell
Root: HKLM; Subkey: SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved; ValueType: string; ValueName: {{B456DBA6-7BF4-478c-937A-05130C2C212E}; ValueData: TortoiseHg; Flags: uninsdeletevalue; Components: shell

; Context menu handlers
Root: HKCR; Subkey: Directory\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: Directory\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell

Root: HKCR; Subkey: Directory\Background\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: Directory\Background\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell

Root: HKCR; Subkey: Drive\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: Drive\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell

Root: HKCR; Subkey: Folder\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: Folder\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell

Root: HKCR; Subkey: *\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: *\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell

Root: HKCR; Subkey: InternetShortcut\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey; Components: shell
Root: HKCR; Subkey: InternetShortcut\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; Components: shell

