# M Language Essentials

The minimum mental model and vocabulary to write correct Power Query (M) for cleaning. M is functional,
case-sensitive, and strongly (if dynamically) typed; almost everything is a value, and tables are the main
value you pass through a chain of transforms.

## `let ... in`

A query is usually one `let` expression: a list of named **steps** (bindings), then `in` returns one of
them (conventionally the last).

```m
let
    Source = Excel.Workbook(File.Contents("C:\data\sales.xlsx"), null, true),
    Sheet  = Source{[Item="Sheet1", Kind="Sheet"]}[Data],
    #"Promoted Headers" = Table.PromoteHeaders(Sheet, [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers", {{"Date", type date}, {"Amt", type number}})
in
    #"Changed Type"
```

- Steps are **immutable** and **order-independent except through references** — `#"Changed Type"` runs after
  `#"Promoted Headers"` only because it names it. Reordering lines with the same references changes nothing.
- A step name that isn't a bare identifier (has spaces, punctuation, or starts with a digit) is written
  `#"Name With Spaces"`. Power BI's UI auto-generates these, so real queries are full of them — keep the
  convention so your additions read natively.

## Values, and the three structured ones

- **Primitive**: `number`, `text`, `logical` (`true`/`false`), `date`/`datetime`/`datetimezone`/`time`/
  `duration`, `null`, `binary`.
- **List** `{1, 2, 3}` — ordered; index with `{0}` (zero-based). `List.Sum`, `List.Distinct`, etc.
- **Record** `[A = 1, B = "x"]` — named fields; access with `[A]`. Rows of a table are records.
- **Table** — the star of cleaning. `t{0}` is the first row (a record); `t[Col]` is a column (a list);
  `t{0}[Col]` is one cell.

## `each`, `_`, and field access

`each EXPR` is sugar for `(_) => EXPR` — a one-argument function. Inside it, `_` is the argument, and a bare
`[Col]` means `_[Col]`. This is why row predicates read so cleanly:

```m
Table.SelectRows(t, each [Region] = "East" and [Amount] > 0)
Table.AddColumn(t, "Net", each [Gross] - [Tax], type number)
```

## Types and type ascription

Types matter for the model (sorting, relationships, DAX). Ascribe them **after** the shape is final:

```m
Table.TransformColumnTypes(t, {{"Order Date", type date}, {"Qty", Int64.Type}}, "en-US")
```

- Common type names: `type text`, `type number`, `Int64.Type`, `type date`, `type datetime`, `type logical`.
- The optional third argument is a **culture** (`"en-US"`, `"de-DE"`, ...). Pass it whenever a date/number
  string could be parsed differently by locale — silent locale assumptions are a top cause of wrong dates.
- A value that won't convert becomes an **`Error` cell** (not a crash). See error handling below.

## Errors: `try ... otherwise`

A failing expression yields an error value that propagates through the row. Handle it deliberately:

```m
try Number.FromText([Code]) otherwise null          // per-cell fallback
Table.RemoveRowsWithErrors(t, {"Qty"})              // drop rows whose Qty errored
Table.ReplaceErrorValues(t, {{"Qty", 0}})           // replace error cells with 0
```

## The handful of functions that cover most cleaning

| Goal | Function |
|------|----------|
| Pick / drop columns | `Table.SelectColumns`, `Table.RemoveColumns` |
| Rename columns | `Table.RenameColumns(t, {{"old","new"}})` |
| Filter rows | `Table.SelectRows(t, each <pred>)` |
| Deduplicate | `Table.Distinct(t)` or `Table.Distinct(t, {"Key"})` |
| Set types | `Table.TransformColumnTypes(t, {{...}}, culture)` |
| Transform a column's values | `Table.TransformColumns(t, {{"Col", Text.Trim, type text}})` |
| Add a computed column | `Table.AddColumn(t, "New", each <expr>, type)` |
| Replace values | `Table.ReplaceValue(t, old, new, Replacer.ReplaceText, {"Col"})` |
| Fill blanks down/up | `Table.FillDown(t, {"Col"})`, `Table.FillUp` |
| Split a column | `Table.SplitColumn(t, "Col", Splitter.SplitTextByDelimiter("-"))` |
| Unpivot | `Table.UnpivotOtherColumns(t, {"Key"}, "Attribute", "Value")` |
| Pivot | `Table.Pivot(t, List.Distinct(t[Attr]), "Attr", "Value")` |
| Group & aggregate | `Table.Group(t, {"Key"}, {{"Total", each List.Sum([Amt]), type number}})` |
| Combine queries (stack) | `Table.Combine({a, b})` |
| Join queries | `Table.NestedJoin(a, {"k"}, b, {"k"}, "b", JoinKind.LeftOuter)` then `Table.ExpandTableColumn` |

Text helpers used constantly: `Text.Trim`, `Text.Clean` (strips non-printable), `Text.Upper`/`Lower`/
`Proper`, `Text.Replace`, `Text.Start`/`End`/`Middle`, `Text.PadStart`. Reach for the named transform over a
hand-rolled `AddColumn`+filter — it reads clearer and folds better (see `pitfalls.md` on query folding).
