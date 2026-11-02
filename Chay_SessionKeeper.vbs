Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "pythonw.exe """ & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\app.py""", 0, False
