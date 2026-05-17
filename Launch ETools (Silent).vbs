' Launch ETools with no visible console window.
' Browser opens automatically.
' If something goes wrong, run "Launch ETools.bat" instead to see the logs.

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = scriptDir & "\Launch ETools.bat"

' Run the .bat with a hidden window (intWindowStyle=0).
shell.Run """" & batPath & """", 0, False
