---
name: dax-and-engine-gotchas
description: "Runtime pitfalls hit while building DAX generate/validate/write — Chinese VARs, multi-measure, table vs measure, .NET types, streaming"
metadata: 
  node_type: memory
  type: reference
  originSessionId: e80f40ac-f90a-4270-8df9-75af5b2a0958
---

Hard-won runtime gotchas from building the DAX generate→validate→write pipeline (all fixed in code; recording the *why* so they're not re-introduced):

1. **Chinese VAR names are invalid DAX.** `VAR 当前实际 = …` → engine error "Invalid token … 当". Variable names must be ASCII identifiers; measure/column names may be Chinese. The chat prompt forbids non-ASCII VAR names. Verified against the engine.

2. **Measure (scalar) ≠ calculated table (table expr) — different objects.** A date table like `Dim_Date = CALENDAR(...)` returns a table; running it as a measure gives "该表达式引用多列，多列不能转换为标量值". Detect with `is_table_expression` (leading table-returning function), validate via `EVALUATE <expr>` (not `EVALUATE ROW`), and write via TOM `Tables.Add`+CalculatedPartitionSource (not `Measures.Add`). See [[write-back-via-tom]].

3. **Splitting a multi-measure block on `Name =` is fragile — we abandoned it for ONE measure per ```dax block (2026-06-25).** Models emit several measures plus prose; the old `split_measures` cut on every line that looked like `Name =`, which shattered real measures because: (a) **DAX comments** — `//`, `--`, `/* */` — weren't stripped, so a comment like `// Total Change = Price + Volume` was read as a boundary (leaked bare tokens → engine "The syntax for 'Change' is incorrect"); and (b) **`x = "..."` comparisons inside `SWITCH ( TRUE (), … )`** were read as boundaries even though they sit at paren-depth ≥ 1. Two-layer fix, both verified + unit-tested: strip DAX comments in `_strip_noise`; make boundary detection **paren-depth-aware** (`_measure_bounds` only accepts `Name =` at depth 0). **Then the real fix:** stop splitting within a block entirely — `parse_dax_blocks` collects EVERY ```dax block and treats **each block as exactly one object**; the chat prompt now tells the model to emit **one measure/table per ```dax block**. (`split_measures`/`measure_expression` are still used by the single-measure calibrate/capability paths, now depth-aware.)

4. **One broken measure poisons a shared DEFINE.** Validating a set by DEFINE-ing all of them means one syntax error fails them all. `validate_measure_set` first tests each alone, marks the syntactically-broken ones, and excludes them from the others' DEFINE set — so a good derived measure that references valid siblings still validates.

5. **ADOMD returns .NET types that can't be pickled into Streamlit session_state.** `System.DateTime`/`System.Decimal` come back as .NET objects (pythonnet doesn't auto-convert them) → `cannot pickle 'DateTime' object`. `live_source._to_py` converts DateTime→python datetime, Decimal→float, else str. For DAX filter literals, dates format as `DATE(y,m,d)`.

6. **OpenAI-compatible streaming (Doubao) sends a final chunk with empty `choices`.** It carries only usage stats; `chunk.choices[0]` → `IndexError: list index out of range`. Guard `if not chunk.choices: continue` in `openai_compat.stream` (and the same for `complete`).

Part of [[dev-progress-2026-06]]; grounding/run-verify rationale in [[live-evaluate-validation-is-required]].
