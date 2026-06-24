---
name: dax-expert
description: >
  Professional DAX authoring, explanation, and optimization for Power BI / Tabular models.
  Use this skill whenever the task involves writing, generating, reviewing, explaining, debugging,
  or performance-tuning a DAX measure, calculated column, or DAX query — including translating a
  natural-language business metric ("year-over-year growth", "% of total", "running total", "rolling
  12 months") into a measure, fixing a measure that returns wrong numbers or is slow, or grounding a
  measure in a real model schema so it only references columns/tables that actually exist. Trigger this
  even when the user doesn't say "DAX" explicitly but is clearly asking for a Power BI metric, KPI,
  measure, or time-intelligence calculation. Within the PowerBI AI Assistant project, this skill backs
  the DAX capability (generate / explain / optimize).
license: Internal project skill.
---

# DAX Expert

Write DAX the way a seasoned Tabular/Power BI engineer would: correct first, fast second, readable
throughout. DAX looks like a formula language but behaves like a query engine — most wrong answers
and most slow measures come from misunderstanding **evaluation context**, not from syntax. So reason
about context explicitly before reaching for functions.

## The one rule that prevents most failures: ground everything in the real model

A measure that references a column that doesn't exist is worse than no measure — it looks plausible
and fails at runtime. So:

- **Only reference tables, columns, and measures that are present in the provided model context.**
  If you don't have the schema, ask for it (or, in this project, load it via the `ContextSource`)
  before writing anything. Never invent `Sales[Amount]` because it "should" be there.
- Use fully-qualified column references `Table[Column]` and bare measure references `[Measure]`.
  This isn't cosmetic: `Table[Column]` vs `[Measure]` signals intent and avoids ambiguity, and the
  `[Measure]` form carries an implicit `CALCULATE` (context transition) that you must reason about.
- Reuse existing base measures instead of re-deriving aggregations. If `[Total Sales]` exists, build
  `[Sales YoY %]` on top of it rather than re-writing `SUM(Sales[Amount])` everywhere. This keeps the
  model consistent and makes one fix propagate.
- Prefer **measures over calculated columns** unless the value must be materialized for a relationship,
  slicer, or axis. Calculated columns cost memory and are computed at refresh; measures compute at
  query time in the current context.

## Reason about evaluation context before writing

Two contexts, and the bridge between them, explain almost everything:

- **Row context** — "the current row." Exists inside calculated columns and iterators (`SUMX`,
  `AVERAGEX`, `FILTER`, `ADDCOLUMNS`, ...). Row context does **not** filter the model by itself.
- **Filter context** — "what is currently visible." Set by the visual (slicers, rows/columns),
  by `CALCULATE` filter arguments, and by filter functions. Aggregations see only rows allowed by
  the filter context.
- **Context transition** — `CALCULATE` (and every measure reference, which wraps an implicit
  `CALCULATE`) converts the current row context into an equivalent filter context. This is *why*
  `SUMX(Customers, [Total Sales])` gives per-customer sales: each row's customer becomes a filter.
  It's also the most common source of surprise and of slowness — so whenever you put a measure
  reference inside an iterator, say to yourself "context transition happens here" and confirm that's
  what you want.

There is one nested-iterator trap worth burning into memory because it survives static review: when
you iterate one table and aggregate a **different** table inside (e.g. `AVERAGEX(VALUES('Date'[Date]),
SUMX('Inventory', ...))`), the outer row context does **not** filter the inner table. Without a
`CALCULATE` (or a measure reference) to transition it, the inner aggregation silently ignores the
current row and recomputes over the whole period — code that *reads* as per-day but isn't. Wrap the
inner expression in `CALCULATE`. This bug looks self-consistent, so prove it by running the measure,
not by re-reading it. Full treatment in `references/context-and-evaluation.md` §11.

When a result is wrong, diagnose by asking: *what is the filter context at the point of evaluation,
and did a context transition change it?* See `references/context-and-evaluation.md` for the deeper
treatment (CALCULATE filter modifiers, `KEEPFILTERS`, `ALL`/`REMOVEFILTERS`/`ALLSELECTED`, expanded
tables, and the evaluation order of `VAR`s).

## Authoring conventions (these are also performance and correctness habits)

- **Use `VAR` generously.** Variables make logic readable, avoid recomputing the same subexpression,
  and — critically — they are evaluated **where they are defined, in that context**, then treated as
  constants. This lets you capture a value *before* a `CALCULATE` changes the context. Name them for
  meaning (`_priorYearSales`, not `_x`).
- **Always `DIVIDE(numerator, denominator)` instead of `/`.** `DIVIDE` returns blank (or your chosen
  alternate) on divide-by-zero instead of erroring. Ratios are everywhere in BI; this single habit
  removes a whole class of breakage.
- **Filter with predicates, not whole-table `FILTER`, when you can.**
  `CALCULATE([Total Sales], Sales[Region] = "East")` lets the engine apply an efficient column filter.
  `CALCULATE([Total Sales], FILTER(Sales, Sales[Region] = "East"))` forces a row-by-row scan of the
  whole table. Reserve `FILTER` for conditions the simple form can't express, and then filter the
  smallest thing possible (`FILTER(VALUES(Sales[Region]), ...)`), not the whole fact table.
- **Add to the filter context with `KEEPFILTERS`, clear it with `REMOVEFILTERS`/`ALL`.** Know which
  one you mean. A `% of total` clears a grouping; a "within the current selection" total keeps it.
- **Time intelligence needs a proper Date table** marked as a date table, with one contiguous row per
  day covering the data range. If the model has none, say so — `SAMEPERIODLASTYEAR`, `DATESYTD`, etc.
  are unreliable without it.
- **Format the code** for readability: one clause per line, `VAR`/`RETURN` aligned, function arguments
  broken across lines when long. Future readers (including the next model) debug formatted DAX faster.

## The three core actions

This skill backs three tasks. Match the output to the task.

### Generate (natural language → measure)

1. Restate the business definition in one sentence, including the grain and any filters implied
   ("net sales, current filter context, excluding returns"). Surfacing assumptions is how you catch
   a mismatch before writing 20 lines.
2. Identify the base measures/columns it should build on, from the model context.
3. Write the measure using the conventions above. Reach for a known pattern from
   `references/measure-templates.md` rather than improvising time-intelligence from scratch.
4. Output **(a)** the measure in a `dax` code block with a suggested name, **(b)** a 1–3 sentence
   plain-language explanation of how it behaves, and **(c)** any assumption the user should confirm
   (e.g., "assumes a marked Date table named `'Date'`").

### Explain (measure → understanding)

Walk through it in evaluation order: what each `VAR` captures and in what context, what the filter
context is when the aggregation runs, where any context transition occurs, and what the final
`RETURN` produces. Explain the *why*, not just a function glossary. Call out any subtle behavior
(blanks, context transition, filter modifiers) the reader might miss.

### Optimize (measure → faster/cleaner measure)

Scan for the anti-patterns catalogued in `references/performance.md` (whole-table `FILTER`, `/`
instead of `DIVIDE`, repeated subexpressions, unnecessary calculated columns, redundant `CALCULATE`,
expensive context transition inside iterators, `FORMAT` producing text used numerically, etc.).
Produce: the rewritten measure, then a short bullet list of *what changed and why it's faster or
safer* — verified by reasoning, not asserted. If a "fix" only improves readability and not
performance, say that honestly rather than claiming a speedup.

## Validate before declaring done

- Every `Table[Column]` and `[Measure]` referenced exists in the model context.
- Parentheses and function arities are balanced/correct.
- Division is via `DIVIDE`; time intelligence has a Date table to rely on.
- The measure returns a scalar of the expected type (don't return text from `FORMAT` where a number
  is expected).
- For any **nested iterator over a date/dimension table**, confirm the inner aggregation is wrapped in
  `CALCULATE` (or is a measure) so context transition actually scopes it to the current row — see the
  trap above. This class of error compiles and looks correct, so it is exactly what real execution is
  for.
- In this project, when a live connection is available, the measure can additionally be confirmed by
  running it as a DAX query (`DEFINE MEASURE ... EVALUATE ROW(...)`). Prefer real execution over
  assertion whenever you can get it.

## Reference files

Read these when the task needs the detail; don't inline their full contents into every answer.

- `references/measure-templates.md` — ready-to-adapt patterns: time intelligence (YoY, YTD, rolling
  N, prior period), ratios & % of total, running/cumulative totals, ranking, distinct counts,
  semi-additive (balances), and "current selection" totals.
- `references/performance.md` — anti-pattern → fix catalog with before/after, and how to think about
  the storage-engine vs formula-engine split.
- `references/context-and-evaluation.md` — deep dive on row/filter context, context transition,
  `CALCULATE` filter modifiers, `ALL` family, expanded tables, and common "wrong number" diagnoses.
