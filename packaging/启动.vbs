' Power BI Assistant - silent launcher.
' Double-click this to start the app with NO black console window.
' It runs the .bat in this same folder hidden (window style 0), no wait.
' ASCII-only on purpose; it locates the .bat by extension so no Chinese literal is needed.
Dim fso, sh, folder, f, batPath
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = ""
For Each f In fso.GetFolder(folder).Files
  If LCase(fso.GetExtensionName(f.Name)) = "bat" Then batPath = f.Path
Next
If batPath <> "" Then
  sh.Run "cmd /c """ & batPath & """", 0, False
Else
  MsgBox "Launcher .bat not found next to this script.", 16, "Power BI Assistant"
End If
