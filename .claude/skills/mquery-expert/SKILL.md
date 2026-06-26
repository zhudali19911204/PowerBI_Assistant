---
name: mquery-expert
description: >
  Professional Power Query (M) authoring for Power BI data cleaning and shaping. Use this skill whenever
  the task involves writing, generating, reviewing, explaining, or fixing an M query / step — including
  cleaning a table (remove blank or duplicate rows, trim/clean text, fix data types, split or merge
  columns, unpivot/pivot, group & aggregate, replace values, fill down, handle errors), reshaping or
  combining queries (merge/append), or grounding a transformation in a query's real output columns so it
  only references columns that actually exist. Trigger this even when the user doesn't say "Power Query"
  or "M" explicitly but is clearly asking to clean, transform, reshape, or prepare source data in Power BI
  before it enters the model. Within the PowerBI AI Assistant project, this skill backs the data-cleaning
  capability (clean / explain).
license: Internal project skill.
---

# Power Query (M) Expert

Write M the way a seasoned Power BI data engineer would: correct first, foldable and refresh-safe second,
readable throughout. Power Query is a **functional, lazily-evaluated** language built around a `let`
expression whose steps are immutable bindings — each step is a value (usually a table) computed from the
previous one. Most cleaning bugs come from referencing a column that doesn't exist *yet* at that step, or
from a type/locale mismatch — not from exotic functions. So reason about **what each step produces**
before reaching for transforms.

## The one rule that prevents most failures: ground every step in the real shape

A step that references a column the table doesn't have at that point fails at refresh — and it looks
plausible until it runs. So:

- **Only reference columns that exist in the query's output at the step where you use them.** Column names
  in M are **case-sensitive** and exact (`"Customer Number"`, not `"customer number"`). If you don't have
  the schema, ask for it (in this project it's supplied as the query's current M + its output columns).
  Never invent `"Amount"` because it "should" be there.
- **Build on the existing query, don't rewrite it from the data source.** When asked to clean an existing
  query, append your steps after its current last step (reference it by its step name), so credentials,
  the source connection, and prior shaping are all preserved. Re-deriving `Source = Excel.Workbook(...)`
  from scratch throws away working auth and is almost never what the user wants.
- **Reference other queries by name** as `#"Query Name"` (or a bare identifier if it has no spaces). This
  is how `Merge`/`Append` and staging queries compose; the referenced query's credentials are inherited.
- **Prefer transformations that preserve query folding** when the source is a database (see below) — but
  never sacrifice correctness for folding.

## Reason about M's model before writing

- **`let ... in`** — a `let` binds a sequence of named steps; `in` returns one of them (usually the last).
  Steps are just variables; order matters only through references, not position. A step name with spaces
  or punctuation must be quoted: `#"Changed Type"`. Power BI's UI auto-names steps this way, so most real
  queries are full of `#"..."` references — keep that convention so your additions read natively.
- **Lazy + immutable** — nothing is mutated; each transform returns a *new* table. `Table.RemoveRows`,
  `Table.SelectColumns`, etc. take a table and give back a table. This is why you chain steps rather than
  edit in place.
- **Types are explicit and matter.** `Table.TransformColumnTypes(t, {{"Col", type number}})` ascribes
  types; a wrong ascription (text that won't parse as a date, or a locale mismatch) surfaces as `Error`
  cells, not a hard failure — so they hide until you look. Use the typed transform, and when locale is in
  play pass the culture: `Table.TransformColumnTypes(t, {{"Date", type date}}, "en-US")`.
- **Errors propagate per cell.** A bad conversion yields an `Error` value in that cell; downstream steps
  carry it. Use `try ... otherwise ...`, `Table.RemoveRowsWithErrors`, or `Table.ReplaceErrorValues` to
  handle them deliberately rather than letting them ride into the model.
- **Query folding** — against a database, Power Query pushes compatible steps down into a single source
  query (fast, server-side). Folding-friendly steps (filter, select, rename, group, type) keep it; some
  steps (custom functions, certain merges, `Table.Buffer`) break it, and everything after runs locally.
  Put folding-breakers as late as possible.

## Authoring conventions (these are also correctness and refresh habits)

- **Name steps for meaning**, mirroring Power BI's style: `#"Removed Blank Rows"`, `#"Changed Type"`,
  `#"Filtered Region"`. Readable step names are how the user (and the next model) audit the chain in the
  Applied Steps pane.
- **Set types explicitly** after shaping (promote headers → then `Table.TransformColumnTypes`). Don't
  leave columns as `any`; a typed column is what makes relationships, sorting, and DAX behave.
- **Prefer the specific transform over a generic one**: `Table.SelectColumns` / `Table.RemoveColumns` to
  pick columns, `Table.SelectRows` with a predicate to filter, `Table.Distinct` to dedupe,
  `Table.ReplaceValue` for substitutions, `Table.FillDown` for sparse keys. Reach for the named function;
  it folds better and reads clearer than a hand-rolled `Table.AddColumn` + filter.
- **Filter rows with a predicate**: `Table.SelectRows(t, each [Region] = "East")`. Use `each` and the
  `[Column]` field-access shorthand; for blank/whitespace use `each [Col] <> null and [Col] <> ""`.
- **Keep transforms order-correct**: promote headers *before* setting types; remove columns you won't need
  *early* (smaller table, better folding); set types *after* the shape is final.
- **Be explicit about culture/locale** on date and number parsing when the data could be ambiguous —
  silent locale assumptions are a classic source of wrong dates.

## The two core actions

This skill backs two tasks. Match the output to the task.

### Clean / transform (natural language → M)

1. Restate the cleaning goal in one sentence, naming the columns involved and the output shape
   ("drop rows where Customer Number is blank, then type Order Date as date"). Surfacing assumptions
   catches a column-name or grain mismatch before writing ten steps.
2. Start from the query's current last step (reference it), then add the minimal sequence of named steps
   that achieves the goal, using the conventions above.
3. Output **(a)** the M in a `powerquery` code block — a full `let ... in` query that begins from the
   existing query and ends at the cleaned result, **(b)** a 1–3 sentence plain-language explanation of
   what the new steps do, and **(c)** any assumption to confirm (e.g. "assumes Order Date is text in
   `M/D/YYYY`").

### Explain (M → understanding)

Walk the `let` chain step by step: what each step receives, the transform it applies, and the resulting
shape (columns added/removed/retyped). Explain the *why* and flag anything subtle: a type ascription that
could error, a step that breaks folding, a locale-dependent parse, an `each` predicate that drops more
than intended.

## Validate before declaring done

- Every column name referenced exists in the table at that step, spelled and cased exactly.
- The query is a single well-formed `let ... in` (balanced parentheses/brackets/quotes; every `#"..."`
  step or query reference is defined or really exists).
- Types are ascribed after shaping; date/number parses that depend on locale pass a culture.
- Errors are handled deliberately where a conversion could produce them.
- The output shape (columns + types) matches what the request asked for.
- In this project, when a live Desktop connection is available, the query can additionally be confirmed by
  **writing it to a temporary table, refreshing it, and reading back the output schema** (and any engine
  error). Prefer real execution over assertion whenever you can get it — an M query that *reads* correctly
  can still fail at refresh on a type or a missing column.

## Reference files

Read these when the task needs the detail; don't inline their full contents into every answer.

- `references/m-language-essentials.md` — `let/in`, step references, types & type ascription, `each`/`_`,
  records/lists/tables, `try/otherwise`, and the handful of functions that cover most cleaning.
- `references/cleaning-recipes.md` — ready-to-adapt step sequences: remove blank/duplicate rows, trim &
  clean text, fix types (with culture), split/merge columns, unpivot/pivot, group & aggregate, replace
  values, fill down, merge & append queries, conditional columns.
- `references/pitfalls.md` — the traps: case-sensitive column names, locale/type-parse errors, error-cell
  propagation, query-folding breakers, and rewriting-from-source vs building-on-the-existing-query.
