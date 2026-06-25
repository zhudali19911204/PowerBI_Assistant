---
name: write-back-via-tom
description: "How write-back to the open Power BI Desktop model works — TOM (not bundled), downloaded from NuGet, for measures AND calculated tables"
metadata: 
  node_type: memory
  type: reference
  originSessionId: e80f40ac-f90a-4270-8df9-75af5b2a0958
---

Writing a measure or calculated table into the **open** Power BI Desktop model works and is proven on the user's machine (`context/live_writer.py` `LiveDesktopWriter`). Changes land in the running model; the user presses **Ctrl+S in Desktop** to persist to the .pbix. We only ever write DAX that already passed live validation.

**Mechanism = TOM (Tabular Object Model), not TMSL-over-ADOMD.**
- TMSL `create`/`createOrReplace` of a *single measure* via `AdomdCommand` is **rejected** by the Desktop engine ("Unrecognized JSON property: measure"). The endpoint DOES accept TMSL DDL (it's not read-only), but single-measure DDL isn't supported there — so use TOM.
- TOM is `Microsoft.AnalysisServices.Tabular.dll`, which Power BI does **NOT** bundle (only the ADOMD client is in its bin). We download the NuGet package `microsoft.analysisservices.retail.amd64` (pinned 19.84.1) once, extract the four `lib/net45/` DLLs, cache them under `~/.powerbi_ai_assistant/lib/amo`, and load via pythonnet (`context/amo.py` `ensure_amo_dlls`). Download goes through `enable_os_trust_store()` so it works behind the corporate proxy ([[corporate-tls-inspection-needs-truststore]]).

**TOM usage (proven):**
- Measure: `server.Connect("Data Source=localhost:PORT")` → `server.Databases[0].Model` → find table → `table.Measures.Add(measure)` (or set `existing.Expression`) → `model.SaveChanges()`.
- Calculated table (date table): create `Table`, a `Partition` whose `Source` is a `CalculatedPartitionSource` with `.Expression = <table DAX>`, `model.Tables.Add(table)`, `SaveChanges()` — the engine infers the columns automatically.

**pythonnet gotchas (apply to ADOMD and TOM both):** `import clr` must run before `import System`. `clr.AddReference` does NOT resolve assemblies from `sys.path` in pythonnet 3 — use `Assembly.LoadFrom(dll)` then `asm.GetType("Microsoft.AnalysisServices.Tabular.<X>")` + `System.Activator.CreateInstance`. Pass an explicit `System.Array[System.Object]([...])` to Activator or it picks the wrong overload. The ADOMD client assembly is *named* `Microsoft.PowerBI.AdomdClient` but its types keep the original `Microsoft.AnalysisServices.AdomdClient` namespace ([[live-connection-works-via-bundled-adomd]]).

Ties to [[dev-progress-2026-06]] and the grounding-first/run-verify principles ([[live-evaluate-validation-is-required]]).
