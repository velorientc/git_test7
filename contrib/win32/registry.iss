[Registry]
; rpc server autostart on logon
Root: HKLM; Subkey: Software\Microsoft\Windows\CurrentVersion\Run; ValueType: string; ValueName: TortoiseHgRpcServer; Flags: uninsdeletevalue; ValueData: {app}\thgtaskbar.exe

; register TortoiseHg config info
Root: HKLM; Subkey: Software\TortoiseHgShell;  Flags: uninsdeletekey
Root: HKLM; Subkey: Software\TortoiseHgShell;  ValueType: string; ValueName: ; ValueData: {app}
Root: HKLM; Subkey: Software\TortoiseHg;  Flags: uninsdeletekey
Root: HKLM; Subkey: Software\TortoiseHg;  ValueType: string; ValueName: ; ValueData: {app}

; Icon handler COM controls
;    Normal
Root: HKCR; Subkey: CLSID\{{B456DBA0-7BF4-478c-937A-05130C2C212E}; Flags: uninsdeletekey
Root: HKCR; Subkey: CLSID\{{B456DBA0-7BF4-478c-937A-05130C2C212E}; ValueType: string; ValueName: ; ValueData: TortoiseHg
Root: HKCR; Subkey: CLSID\{{B456DBA0-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ; ValueData: {app}\THgShell.dll
Root: HKCR; Subkey: CLSID\{{B456DBA0-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ThreadingModel; ValueData: Apartment

;    Added
Root: HKCR; Subkey: CLSID\{{B456DBA1-7BF4-478c-937A-05130C2C212E}; Flags: uninsdeletekey
Root: HKCR; Subkey: CLSID\{{B456DBA1-7BF4-478c-937A-05130C2C212E}; ValueType: string; ValueName: ; ValueData: TortoiseHg
Root: HKCR; Subkey: CLSID\{{B456DBA1-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ; ValueData: {app}\THgShell.dll
Root: HKCR; Subkey: CLSID\{{B456DBA1-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ThreadingModel; ValueData: Apartment

;   Modified
Root: HKCR; Subkey: CLSID\{{B456DBA2-7BF4-478c-937A-05130C2C212E}; Flags: uninsdeletekey
Root: HKCR; Subkey: CLSID\{{B456DBA2-7BF4-478c-937A-05130C2C212E}; ValueType: string; ValueName: ; ValueData: TortoiseHg
Root: HKCR; Subkey: CLSID\{{B456DBA2-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ; ValueData: {app}\THgShell.dll
Root: HKCR; Subkey: CLSID\{{B456DBA2-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ThreadingModel; ValueData: Apartment

;   Unversioned
Root: HKCR; Subkey: CLSID\{{B456DBA6-7BF4-478c-937A-05130C2C212E}; Flags: uninsdeletekey
Root: HKCR; Subkey: CLSID\{{B456DBA6-7BF4-478c-937A-05130C2C212E}; ValueType: string; ValueName: ; ValueData: TortoiseHg
Root: HKCR; Subkey: CLSID\{{B456DBA6-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ; ValueData: {app}\THgShell.dll
Root: HKCR; Subkey: CLSID\{{B456DBA6-7BF4-478c-937A-05130C2C212E}\InProcServer32; ValueType: string; ValueName: ThreadingModel; ValueData: Apartment

; The actual icon overlay handlers for Explorer
Root: HKLM; Subkey: Software\TortoiseOverlays\Normal; ValueType: string; ValueName: TortoiseHg; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}
Root: HKLM; Subkey: Software\TortoiseOverlays\Added; ValueType: string; ValueName: TortoiseHg; ValueData: {{B456DBA1-7BF4-478c-937A-05130C2C212E}
Root: HKLM; Subkey: Software\TortoiseOverlays\Modified; ValueType: string; ValueName: TortoiseHg; ValueData: {{B456DBA2-7BF4-478c-937A-05130C2C212E}
Root: HKLM; Subkey: Software\TortoiseOverlays\Unversioned; ValueType: string; ValueName: TortoiseHg; ValueData: {{B456DBA6-7BF4-478c-937A-05130C2C212E}

; Make them approved by administrator
Root: HKLM; Subkey: SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved; ValueType: string; ValueName: {{B456DBA0-7BF4-478c-937A-05130C2C212E}; ValueData: TortoiseHg; Flags: uninsdeletevalue
Root: HKLM; Subkey: SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved; ValueType: string; ValueName: {{B456DBA1-7BF4-478c-937A-05130C2C212E}; ValueData: TortoiseHg; Flags: uninsdeletevalue
Root: HKLM; Subkey: SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved; ValueType: string; ValueName: {{B456DBA2-7BF4-478c-937A-05130C2C212E}; ValueData: TortoiseHg; Flags: uninsdeletevalue
Root: HKLM; Subkey: SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved; ValueType: string; ValueName: {{B456DBA6-7BF4-478c-937A-05130C2C212E}; ValueData: TortoiseHg; Flags: uninsdeletevalue

; Context menu handlers
Root: HKCR; Subkey: Directory\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey
Root: HKCR; Subkey: Directory\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}

Root: HKCR; Subkey: Directory\Background\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey
Root: HKCR; Subkey: Directory\Background\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}

Root: HKCR; Subkey: Drive\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey
Root: HKCR; Subkey: Drive\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}

Root: HKCR; Subkey: Folder\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey
Root: HKCR; Subkey: Folder\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}

Root: HKCR; Subkey: *\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey
Root: HKCR; Subkey: *\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}

Root: HKCR; Subkey: InternetShortcut\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey
Root: HKCR; Subkey: InternetShortcut\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}

;Root: HKCR; Subkey: lnkfile\shellex\ContextMenuHandlers\TortoiseHgCMenu; Flags: uninsdeletekey
;Root: HKCR; Subkey: lnkfile\shellex\ContextMenuHandlers\TortoiseHgCMenu; ValueType: string; ValueName: ; ValueData: {{B456DBA0-7BF4-478c-937A-05130C2C212E}
