---
name: dev-progress-2026-06
description: "What's actually built in the PowerBI AI Assistant as of 2026-06-24 — features, files, what works, what's next"
metadata: 
  node_type: memory
  type: project
  originSessionId: e80f40ac-f90a-4270-8df9-75af5b2a0958
---

Development state as of 2026-06-24 (phase-1 DAX assistant, Streamlit app run via `streamlit run powerbi_ai_assistant/app/main.py`, default port 8501). All of the below is built, tested (pytest ~50 passing, mypy clean), and verified against the user's real open Desktop model.

**Built features**
- **Live model read** (`context/live_source.py` `LiveDesktopSource`): connects to the open Desktop engine, reads tables/columns/relationships/measures via TMSCHEMA DMVs. Live-only — static pbixray was dropped ([[phase1-is-live-only-static-dropped]], [[live-connection-works-via-bundled-adomd]]).
- **Live EVALUATE validation + repair** (`dax/live_eval.py`, `dax/capability.py`): generate → static check → run-verify via `EVALUATE` → auto-repair loop. `run_verified` is honest (never claims execution it didn't do).
- **AI 对话 chat mode** (the old "快速生成", now `_render_dax_chat` in `app/components.py`): grounded multi-turn chat, streaming, a "思考过程" reasoning section (prompt-driven), per-object run-verification, and a **write toggle** (default off) that surfaces a one-click "写入模型" per validated object.
- **校准式生成 (calibrated/oracle-driven)** (`dax/calibrate.py`): user gives a known-correct value at a dimension slice (structured dropdowns, values fetched live); AI generates → evaluates AT the slice → compares → auto-fixes ≤2 rounds then ASKS the user a clarifying question → repeat until it matches. Configurable match tolerance. Post-pass "继续优化" refine loop.
- **Write-back to Power BI** (`context/live_writer.py` `LiveDesktopWriter`): writes measures AND calculated tables (e.g. date tables) into the open model via TOM. See [[write-back-via-tom]].
- **Multi-object handling**: a reply may contain several measures (base+derived) and/or a calculated table; `split_measures` + `is_table_expression` classify each, validate appropriately (measures as a set with sibling DEFINEs, tables via `EVALUATE`), and offer the right write control.
- **UI**: top-left ⚙️ settings dialog (model config), sidebar 🔴/🟢 connection light + field browser (click a column to insert its reference), refined theme (`app/theme.py`, Space Grotesk/Inter/JetBrains Mono, Power-BI gold accent).

**Milestones**: M0–M4, M6, M7 done; calibrated generation + chat + write-back are beyond the original plan. M5 (standalone explain/optimize actions) folded into chat. Phase 2/3 (M cleaning, modeling, dashboards) not started.

**Status (2026-06-25): phase-1 DAX assistant is paused here — "先这样" — it's at a good stopping point.** Packaging for colleagues is also done ([[packaging-distribution-gotchas]]). Distribution UI is light-only with the app-mode-window launcher.

**Phase-2 (data cleaning / Power Query M) STARTED 2026-06-25 — full vertical slice built and proven end-to-end.** New `MQueryCapability` (`powerbi_ai_assistant/mquery/`, mirrors `dax/`: `capability.py`/`generate.py`/`artifact.py`/`live_eval.py`/`prompts.py`) auto-renders as a "数据清洗" tab. Same live-only, grounded, run-verify-then-write-back philosophy as DAX, chosen deliberately over static/pandas-sim options:
- **Read existing M**: `live_source.py` now also reads `TMSCHEMA_PARTITIONS` (each table's M) + `TMSCHEMA_EXPRESSIONS` (params/shared queries); `ModelContext` carries `table_queries`/`shared_expressions` + `serialize_query_for_prompt()`.
- **Generate** grounded M that BUILDS ON the existing query (doesn't rewrite the source connection) → **static lint** (`MScriptArtifact`: balanced brackets/quotes, let/in, #"..." step/query grounding). **⛔ Live refresh verification was built and worked in standalone tests, but REMOVED 2026-06-26: its temp-table probe leaks into Desktop's Mashup doc and crashes Desktop ([[mquery-refresh-verification]]).** So the M assistant is now **read-only** (gen + static lint, `run_verified=False`); the user pastes into the Advanced Editor and Desktop verifies on Apply. This loses phase-2's run-verification differentiator — an honest consequence real execution forced. DAX's `EVALUATE`-based verification is unaffected.
- **Write-back of M: REMOVED 2026-06-25** — it crashes Power BI Desktop (NullReferenceException in the Mashup query navigator; editing Power Query externally on an open Desktop is unsupported). The M assistant instead shows the verified M with a copy button + "paste into 高级编辑器" guidance. DAX measure/calc-table write-back is unaffected (different code path). See [[mquery-refresh-verification]].
- **Knowledge**: new authoritative skill `.claude/skills/mquery-expert/` (SKILL.md + 3 references + evals) ↔ compressed `mquery/prompts.py` (same dual-asset rule). UI: `_render_mquery_chat` in `components.py` (own `mq_*` keys to avoid tab-collision; theme.py extended).
- Tests: `tests/test_mquery.py` (13) — parse, lint, generate→static→repair loop. Total pytest 67 passing.
- Plan file: `C:\Users\uic89469\.claude\plans\zippy-popping-treehouse.md`. Spike: scratchpad `m0_refresh_spike.py`.

**Likely next:**
- **Multi-point calibration for 校准式生成 (user's explicit next-up TODO).** Today calibration pins the measure against ONE known-correct value at ONE slice; the planned enhancement is to let the user supply SEVERAL calibration points (multiple slices/expected values) and require the measure to match all of them — this disambiguates measures that happen to be right at one slice but wrong elsewhere, and forces a more precise requirement. Affects `dax/calibrate.py` (`CalibrationSession` currently holds a single `filters`/`expected`; would become a list of points) and the calibrate UI/prompts.
- Re-add a "batch write measures" button (removed in the table/measure refactor); maybe native reasoning tokens; phase-2 capabilities.

Runtime pitfalls collected in [[dax-and-engine-gotchas]]. Project overview: [[powerbi-ai-assistant-project]].
