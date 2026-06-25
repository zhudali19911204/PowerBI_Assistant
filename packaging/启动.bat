@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Power BI Assistant

rem ===========================================================================
rem  Power BI Assistant launcher (app-mode window).
rem  ASCII-only ON PURPOSE: a UTF-8 .bat with non-ASCII bytes is mis-parsed by
rem  the GBK Windows shell. End-user guide: see the usage README.
rem  Normally launched hidden by the .vbs next to it; can also be run directly.
rem  Python priority: bundled runtime\  >  local .venv\  >  system python.
rem ===========================================================================

cd /d "%~dp0.."

rem Skip Streamlit's first-run "enter your email" prompt (it blocks startup).
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
  > "%USERPROFILE%\.streamlit\credentials.toml" echo [general]
  >> "%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)

set "PY="
if exist "runtime\python.exe" set "PY=runtime\python.exe"
if exist ".venv\Scripts\python.exe" if "%PY%"=="" set "PY=.venv\Scripts\python.exe"
if not "%PY%"=="" goto serve

echo First run: preparing the Python environment (needs internet)...
where python >nul 2>nul
if errorlevel 1 goto nopython
python -m venv .venv
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r packaging\requirements-runtime.txt
if errorlevel 1 goto fail
set "PY=.venv\Scripts\python.exe"

:serve
rem Start the server headless (no auto-browser) only if it is not already up; log to a file.
netstat -ano | findstr ":8501" | findstr "LISTENING" >nul 2>nul
if errorlevel 1 (
  start "" /b "%PY%" -m streamlit run powerbi_ai_assistant\app\main.py --server.port 8501 --server.headless true > "%TEMP%\pbi_helper.log" 2>&1
)

rem Wait until the port accepts connections (up to ~40s).
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 60 -and -not $ok;$i++){try{$c=New-Object Net.Sockets.TcpClient;$c.Connect('localhost',8501);$c.Close();$ok=$true}catch{Start-Sleep -Milliseconds 700}}; if(-not $ok){exit 1}"

rem Locate Edge.
set "EDGE="
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"

if not defined EDGE goto fallback

rem Clean stale app profiles from previous runs (cannot delete one in use; harmless).
for /d %%d in ("%TEMP%\PBIHelperEdge_*") do rd /s /q "%%d" >nul 2>nul

rem A UNIQUE user-data-dir forces a brand-new Edge process, so /wait truly blocks
rem until the app window is closed (a shared dir would hand off and return at once).
set "UDD=%TEMP%\PBIHelperEdge_%RANDOM%%RANDOM%"
start /wait "" "!EDGE!" --app=http://localhost:8501 --new-window --no-first-run --no-default-browser-check --user-data-dir="!UDD!"
rd /s /q "!UDD!" >nul 2>nul
goto stop

:fallback
rem No Edge -> default browser; keep a visible window so the user can stop the app.
start "" http://localhost:8501
echo.
echo App opened in your default browser. Close THIS window to stop the app.
pause

:stop
rem App window closed -> stop the Streamlit server (whatever is listening on 8501).
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8501" ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>nul
exit /b 0

:nopython
echo [ERROR] Python not found and no bundled runtime\ folder.
pause
exit /b 1

:fail
echo [ERROR] Setup failed. Check your network and retry.
pause
exit /b 1
