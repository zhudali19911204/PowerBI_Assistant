# Pitfalls

The traps that make an M query *read* correctly but fail (or silently corrupt data) at refresh. These are
exactly what the project's live refresh round-trip is there to catch — but knowing them up front avoids the
round-trips.

## Column names are case-sensitive and exact

`[customer number]` ≠ `[Customer Number]`. M will not "helpfully" match a near-miss; it raises
`[Expression.Error] 找不到表的"…"列 / The column '…' of the table wasn't found`. Copy names from the grounding
verbatim, including spaces and `&`/punctuation. Same for step references `#"..."` and query references.

## Locale / type-parse silently produces Error cells

`Table.TransformColumnTypes(t, {{"Date", type date}})` with `"3/4/2024"` parses differently under `en-US`
(Mar 4) vs `de-DE` (would fail) vs `en-GB` (4 Mar). A value that won't parse becomes an **Error cell**, not a
hard failure — so a wrong culture can quietly turn half a column to errors that only surface downstream. Pass
the culture explicitly when the data could be ambiguous: `(..., "en-US")`. For numbers with thousands
separators or comma decimals, the culture matters just as much.

## Error cells propagate

One bad conversion doesn't stop the query — the Error rides in that cell into the model, where it shows as an
error in visuals or breaks a relationship. Decide a policy at the point of conversion: `try … otherwise …`
for a fallback, `Table.RemoveRowsWithErrors` to drop them, or `Table.ReplaceErrorValues` to substitute. Don't
leave them implicit.

## Rewriting from source vs building on the existing query

When asked to clean an existing query, **append steps onto its last step** — keep its `Source = …` and prior
shaping intact. Rewriting `Source = Excel.Workbook(Web.Contents("https://…"))` from scratch throws away the
working data-source connection and its credentials, and risks a different path/sheet/headers. The cleaned
query must remain a complete, self-contained `let … in` (because it *replaces* the query's whole definition),
but it should reproduce the original steps and add to them, not reinvent the source.

## Query folding breakers

Against a database source, Power Query pushes foldable steps (filter, select, rename, type, group) down into
one server-side query — fast. Some operations **break folding**, and everything after them runs locally on the
full pulled dataset:

- custom-function columns and many `each`-with-custom-logic transforms,
- certain merges/joins, `Table.Buffer`, index columns, some `Table.AddColumn` patterns.

Put folding-breakers **as late as possible** so as much work as possible stays on the server. Never sacrifice
correctness for folding, but don't add an early `Table.Buffer` or a custom column that kills it needlessly.

## `Table.SelectRows` predicate drops more than intended

`each [Col] <> ""` does **not** drop nulls; `each [Col] <> null` does **not** drop empty strings. Blank cells
can be either. To remove "blank-ish" rows, check both: `each [Col] <> null and [Col] <> ""`. Whitespace-only
cells need a trim first or `Text.Trim([Col]) <> ""`.

## Step-name references after an edit

If you rename or remove a step, every later `#"Old Name"` reference breaks. When inserting a step in the
middle, rewire the *next* step to reference your new step, and keep the final `in` pointing at the true last
step.

## Adding/removing columns changes the model contract

If your cleaning removes a column that a relationship, measure, or visual depends on, the *query* refreshes
fine but the **model** then shows downstream errors. Flag column removals that touch keys or referenced
columns, and prefer keeping columns unless the user asked to drop them.

## Verifying: schema, not just "it parsed"

An M query that parses can still fail at refresh on a type or a missing column, or succeed but produce the
wrong *shape*. The honest check is to run the real refresh and read back the output columns + types (what
this project's `MQueryEvaluator` does) — then confirm the shape matches the request, not just that no error
was thrown.
