---
name: pbixray-blind-to-calc-table-columns-and-relationships
description: "Static pbixray parsing cannot see calculated tables' columns OR their relationships — only name+DAX; live connection (M6) needed for full grounding"
metadata: 
  node_type: memory
  type: project
  originSessionId: e80f40ac-f90a-4270-8df9-75af5b2a0958
---

Verified on the user's real model (`Approval&Spending_BI_Report.pbix`, 14 tables / 3 calc tables / 55 measures): **pbixray's static .pbix parse is blind to calculated tables.** The 3 calc tables (Dim_Calendar, Para_DimSelect, Dim_Future) are **absent from `tmschema_tables`** (14 rows = only the regular tables) and have **0 columns in `tmschema_columns`**. pbixray only recovers a calc table's **name + defining DAX** (via `dax_tables`).

Consequence for relationships: pbixray resolves relationship endpoints through its table map, which excludes calc tables, so **any relationship with a calc-table endpoint is dropped entirely** — not filtered by our code, dropped by pbixray. On this model pbixray returned 12 relationships and **none** touched a calc table, even though the user definitely built a Dim_Calendar↔fact relationship. The relationship is real; static parsing just can't see it.

**Why this matters:** It's a real, severe grounding gap, not a cosmetic one. If the AI can't see that Dim_Calendar (the date table) relates to the fact tables, it can't ground time-intelligence DAX (YoY / MTD / YTD) — it treats the calendar as isolated. Calc tables are computed by the engine at refresh; their columns and relationships live in runtime structures that a static file parse fundamentally cannot reconstruct.

**How to apply:** This **upgrades the role of M6 live connection from "validation only" to "validation + grounding".** When the .pbix is open in Desktop, the local AS engine holds the fully materialized model — calc-table columns AND relationships are queryable via DMVs (`$SYSTEM.TMSCHEMA_RELATIONSHIPS`, `TMSCHEMA_COLUMNS`, etc.). So `LiveDesktopSource` closes this gap; `PbixFileSource` structurally cannot. Until live is wired: keep flagging calc tables honestly in `serialize_for_prompt` (already done) and consider letting the user manually annotate a calc table's relationships/role, but treat that as a guess, not ground truth. Diagnostic lesson: I twice gave a wrong root cause (first "my allowlist filter dropped it") before checking the raw metadata — verify against `tmschema_tables`/`tmschema_columns` before concluding. Ties to [[live-evaluate-validation-is-required]] and [[powerbi-ai-assistant-project]]; same evidence-first discipline as [[working-style-confirm-and-honest]].
