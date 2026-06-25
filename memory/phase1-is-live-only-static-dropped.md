---
name: phase1-is-live-only-static-dropped
description: "Decision: phase-1 reads the model ONLY via live Desktop connection; static pbixray parsing was dropped entirely"
metadata: 
  node_type: memory
  type: project
  originSessionId: e80f40ac-f90a-4270-8df9-75af5b2a0958
---

**Decision (2026-06-24, user-directed):** the assistant reads the Power BI model **only through a live connection to the open Power BI Desktop engine**. Static `.pbix` parsing via **pbixray was removed entirely** — `PbixFileSource` and its test deleted, `pbixray` dropped from requirements, no static fallback.

**Why:** static parsing's limits are disqualifying for the product's core job. Proven on the user's real model: pbixray returned **12 relationships and missed every relationship involving a calculated table** (e.g. `Fact_Fc_DT[YearMonth]→Dim_Calendar`, `Fact_Budget_DT[YearMonth]→Dim_Calendar`) and reported **0 columns** for calc tables; the live engine returned **43 relationships and Dim_Calendar's 22 columns**. Inaccurate relationships ⇒ the AI cannot ground accurate DAX (especially time-intelligence through the calendar). See [[pbixray-blind-to-calc-table-columns-and-relationships]] for the root cause and [[live-connection-works-via-bundled-adomd]] for the working live mechanism. The user weighed the tradeoff and chose accuracy over the "works on a closed file" convenience of static.

**How to apply:** The accepted cost of live-only is that the model **must be open in Power BI Desktop** (Windows-only; needs `pythonnet`). Don't reintroduce a static fallback — instead, when no live instance is found, show a clear, actionable message ("请在 Power BI Desktop 中打开该报表后重试") rather than degrading to inaccurate static data. This also means the M6 live-`EVALUATE` validation infra is now on the critical path, not optional. Aligns with [[live-evaluate-validation-is-required]] and the project's grounding-first principle ([[powerbi-ai-assistant-project]]).
