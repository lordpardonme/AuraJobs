' ============================================================
' AuraJobs Invisible Background Runner
' Executes AuraJobs without displaying a command prompt window
' ============================================================

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
ScriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
RootDir = fso.GetParentFolderName(ScriptDir)

BatCommand = """" & RootDir & "\run.bat"" --non-interactive --mode Express"
WshShell.Run BatCommand, 0, False
