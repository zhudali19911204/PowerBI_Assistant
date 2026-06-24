---
name: live-connection-works-via-bundled-adomd
description: "Live Desktop AS connection works with ZERO install — load Power BI's own bundled ADOMD DLL via pythonnet; proven on user's machine"
metadata: 
  node_type: memory
  type: project
  originSessionId: e80f40ac-f90a-4270-8df9-75af5b2a0958
---

**Proven on the user's machine (2026-06-24):** a live connection to the running Power BI Desktop Analysis Services engine works with **no Microsoft component install and no admin** — because Power BI ships its own ADOMD client DLL.

Mechanism that worked:
1. **Engine port:** Desktop's local engine is `msmdsrv.exe`. Find its listening port via `netstat -ano` on the msmdsrv PID — here `localhost:61443`. (Store-version Power BI does NOT put a port file at the classic `%LOCALAPPDATA%\Microsoft\Power BI Desktop\AnalysisServicesWorkspaces\...` path; user is the Microsoft Store version: `…\Packages\Microsoft.MicrosoftPowerBIDesktop_8wekyb3d8bbwe`.)
2. **Client DLL (no install):** `Microsoft.PowerBI.AdomdClient.dll` lives in the Power BI bin dir — for the Store app: `C:\Program Files\WindowsApps\Microsoft.MicrosoftPowerBIDesktop_<ver>_x64__8wekyb3d8bbwe\bin\`. It's x64 (matches the 64-bit venv Python). **Gotcha:** the assembly is *named* `Microsoft.PowerBI.AdomdClient` but its types keep the original namespace **`Microsoft.AnalysisServices.AdomdClient`** (AdomdConnection, AdomdCommand, …).
3. **Load it (pythonnet 3):** `pip install pythonnet`. `clr.AddReference("…")` does NOT resolve from `sys.path` in pythonnet 3, and `from Microsoft… import` after `Assembly.LoadFrom` fails (import hook not registered). What works: `asm = Assembly.LoadFrom(dll)`, `t = asm.GetType("Microsoft.AnalysisServices.AdomdClient.AdomdConnection")`, then `System.Activator.CreateInstance(t, System.Array[System.Object](["Data Source=localhost:PORT"]))` — pass an explicit `object[]` or pythonnet picks the wrong `CreateInstance(string,string)` overload. Then `conn.Open()`, `cmd = conn.CreateCommand(); cmd.CommandText = dax; rdr = cmd.ExecuteReader()`.
4. **Read the model via DMVs:** `SELECT … FROM $SYSTEM.TMSCHEMA_TABLES / TMSCHEMA_COLUMNS / TMSCHEMA_RELATIONSHIPS / TMSCHEMA_MEASURES`. DMV SQL is restricted — **no nested subqueries** (a `SELECT … WHERE x=(SELECT …)` returns "点表达式不允许"); resolve IDs→names in two steps in Python. Auto-date noise tables (`LocalDateTable_*`, `DateTableTemplate_*`) appear here too and should be filtered.

**Why this matters:** This is the green light for `LiveDesktopSource`. It closes the static-parse grounding gap (see [[pbixray-blind-to-calc-table-columns-and-relationships]]): live gave 43 relationships incl. `Fact_Fc_DT[YearMonth]→Dim_Calendar` and Dim_Calendar's 22 columns, vs pbixray's 12 relationships / 0 calc-table columns. Same connection also enables live `EVALUATE` validation (the M6 hard requirement, [[live-evaluate-validation-is-required]]).

**How to apply when building LiveDesktopSource:** discover the DLL dynamically (glob WindowsApps `Microsoft.MicrosoftPowerBIDesktop_*_x64__*/bin/Microsoft.PowerBI.AdomdClient.dll`, and also the non-Store path `C:\Program Files\Microsoft Power BI Desktop\bin\`); discover the port from the msmdsrv PID; if multiple Desktop instances are open, let the user pick. Add `pythonnet` to requirements as a Windows-only/optional dep, import guarded so the app still runs (static fallback) when it's absent. Design: **live-preferred, static (pbixray) fallback** — never live-only, since live needs the file open. Part of [[powerbi-ai-assistant-project]].
