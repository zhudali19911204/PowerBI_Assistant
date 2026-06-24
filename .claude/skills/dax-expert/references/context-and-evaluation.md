# Evaluation context, CALCULATE, and "wrong number" diagnosis

> Distilled in original wording from the SQLBI body of knowledge — *The Definitive Guide to DAX*
> (Russo & Ferrari), the SQLBI articles, and daxpatterns.com. Concepts and techniques are summarized
> here; no source text is reproduced verbatim. Use this when a measure returns the wrong number, or
> when you need to reason precisely about how a calculation evaluates.

## Table of contents
1. The two evaluation contexts
2. Row context
3. Filter context
4. Context transition (the crux)
5. CALCULATE: semantics and order of operations
6. CALCULATE filter modifiers
7. The ALL family and data lineage
8. Expanded tables and relationships
9. Variables and evaluation order
10. A diagnostic checklist for wrong numbers
11. The nested-iterator trap (looks per-row, silently isn't)

---

## 1. The two evaluation contexts
Every DAX expression evaluates inside a context made of two independent parts:
- **Filter context** — the set of rows currently *visible* in each table.
- **Row context** — a *current row* being iterated.

They are independent: you can have one, both, or neither. The classic confusion ("why is my
calculated column not filtering?" / "why does my measure ignore the row I'm on?") comes from assuming
one implies the other. It doesn't — only **context transition** connects them (section 4).

## 2. Row context
- Created automatically inside **calculated columns** and inside any **iterator** (`SUMX`, `AVERAGEX`,
  `MINX`, `RANKX`, `FILTER`, `ADDCOLUMNS`, `GENERATE`, ...).
- It exposes the value of each column **for the current row only**. It does **not** restrict what
  aggregations see — a bare `SUM(Sales[Amount])` inside a row context still sums the entire (filtered)
  table, not "this row".
- Nested iterators create nested row contexts. Use `EARLIER` rarely — prefer `VAR` to capture the
  outer row's value, which is clearer and avoids subtle bugs.

## 3. Filter context
- Set by the report (slicers, the rows/columns/legend of a visual, cross-filtering from other
  visuals), and by `CALCULATE` filter arguments.
- Aggregations read it: `SUM(Sales[Amount])` sums only rows allowed by the current filter context.
- A measure dropped in a matrix is evaluated once per cell, each time under that cell's filter context.
  "The measure is right in the total but wrong per row" is almost always a filter-context story.

## 4. Context transition (the crux)
`CALCULATE` performs **context transition**: it takes the *current row context* and turns it into an
equivalent *filter context* before evaluating its expression. Two consequences you must internalize:

- **Every measure reference has an implicit `CALCULATE`.** So writing `[Total Sales]` inside an
  iterator triggers context transition automatically. `SUMX(Customers, [Total Sales])` works precisely
  because each customer row transitions into a filter on that customer.
- Context transition filters by **all columns of the current row of the (expanded) table**, using the
  row's actual values — including, on a table with a unique key, an effective filter down to that one
  row. This is powerful and also the main cause of unexpected slowness inside big iterators.

Rule of thumb: any time a measure reference or explicit `CALCULATE` sits inside a row context, stop and
ask "context transition happens here — is that the grain I want, and can the engine afford it?"

## 5. CALCULATE: semantics and order of operations
`CALCULATE(<expression>, <filter1>, <filter2>, ...)` evaluates roughly in this order:
1. Evaluate the **filter arguments** in the *outer* context (filters are independent of each other).
2. Perform **context transition** if a row context exists.
3. Apply `CALCULATE` modifiers (`USERELATIONSHIP`, `CROSSFILTER`, `ALL*`, `KEEPFILTERS`) — modifiers
   are applied in a defined precedence, not left-to-right like normal filters.
4. Combine the new filters with the existing filter context (overwrite by default; see `KEEPFILTERS`).
5. Evaluate `<expression>` in the resulting context.

Two practical implications:
- A boolean filter like `Sales[Region] = "East"` is **syntax sugar** for
  `FILTER(ALL(Sales[Region]), Sales[Region] = "East")` — note the `ALL`: it *replaces* any existing
  filter on `Sales[Region]`. That's why `CALCULATE([Sales], Product[Color]="Red")` shows red sales
  even if the visual was filtered to blue.
- Filters on the **same column** from different sources overwrite; use `KEEPFILTERS` to intersect.

## 6. CALCULATE filter modifiers
- **`KEEPFILTERS(<filter>)`** — *intersect* the new filter with the existing one instead of replacing.
  Use for "narrow within what's already selected".
- **`REMOVEFILTERS(<table|column>)`** — clear filters (the modern, intent-revealing name for `ALL`
  used as a `CALCULATE` modifier). Foundation of `% of total`.
- **`ALLEXCEPT(table, col1, ...)`** — clear all filters on the table *except* the listed columns. Handy
  but error-prone with new columns; often `REMOVEFILTERS` on specific columns is clearer.
- **`USERELATIONSHIP(c1, c2)`** — activate an inactive relationship for this evaluation (e.g., ship
  date vs order date role-playing dimension).
- **`CROSSFILTER(c1, c2, direction)`** — change cross-filter direction (both/single/none) locally
  instead of polluting the model with bidirectional relationships.

## 7. The ALL family and data lineage
- `ALL(table)` / `ALL(column)` return a table ignoring filters; as a `CALCULATE` modifier they remove
  filters. As a table function they're used inside `FILTER`, `RANKX`, etc.
- `ALLSELECTED` returns the values visible **outside the current visual's own iteration** — i.e., what
  the user selected via slicers/filters, ignoring the row/column grouping of the current visual. It's
  the right tool for "share of the visible selection" and for stable denominators in running totals.
- **Data lineage**: a column carried through table functions keeps its identity, so a one-column table
  built from `Date[Date]` will *filter* `Date[Date]` when used as a `CALCULATE` filter. Lineage is why
  `TREATAS` works and why `SELECTCOLUMNS`-renamed columns can lose their filtering power.

## 8. Expanded tables and relationships
- A base table is conceptually **expanded** to include the columns of all tables on the one-side it can
  reach via relationships. Filtering an expanded table filters the related dimensions too — this
  underlies a lot of "why did my filter propagate?" behavior.
- Relationships propagate filters from the **one** side to the **many** side by default. To go the
  other way for a single calculation, prefer `CROSSFILTER`/bidirectional *locally* over enabling
  model-wide bidirectional filtering, which is slow and creates ambiguity.
- Many-to-many and bidirectional setups can produce non-additive or ambiguous results; model
  deliberately (bridge tables) rather than relying on auto-detected relationships.

## 9. Variables and evaluation order
- A `VAR` is evaluated **once**, **at the point of definition**, **in the context that exists there**,
  then behaves as a constant wherever it's used. This is the cleanest way to "freeze" a value before a
  `CALCULATE` changes the context (e.g., capture `[Total Sales]` of the current period before shifting
  to last year).
- Variables are **lazy** (not computed if never used) but never recomputed once evaluated. Decompose
  complex measures into named variables — it improves both readability and performance and makes
  explanation trivial.

## 10. A diagnostic checklist for wrong numbers
When a measure is wrong, walk these in order:
1. **What is the filter context** at the cell in question? (Visual grouping + slicers + page/report
   filters + any `CALCULATE` above.)
2. **Is there a row context**, and does a **context transition** convert it? (Measure refs / explicit
   `CALCULATE` inside iterators.)
3. **Did a filter overwrite vs intersect** what you intended? (Boolean filter `ALL` behavior →
   consider `KEEPFILTERS`.)
4. **Time intelligence**: is there a *marked* Date table with contiguous dates, and is the relationship
   active? Without it, `SAMEPERIODLASTYEAR`/`DATESYTD` silently misbehave.
5. **Blanks vs zero**: blank propagates and is excluded from some aggregations; decide intentionally.
6. **Lineage**: if you built a filter table, does its column still have the lineage needed to filter
   the target?
7. **Nested iterator**: if you iterate one table and aggregate another inside, is there a `CALCULATE`
   (or measure reference) doing the context transition? If not, see section 11 — this is the single
   most deceptive bug because the code reads as if it were per-row.

## 11. The nested-iterator trap (looks per-row, silently isn't)
This is the bug that static review — human or LLM — misses most often, because the code *reads*
correctly and even seems to explain itself. It surfaces whenever you iterate one table and, inside,
aggregate a **different** table.

Consider a daily-snapshot inventory averaged over the days of a period:
```dax
-- WRONG: looks like a per-day average, silently returns the whole-period total instead
Avg Inventory Value =
AVERAGEX (
    VALUES ( 'Date'[Date] ),                          -- row context over dates
    SUMX ( 'Inventory', 'Inventory'[Units On Hand] * RELATED ( 'Product'[Standard Cost] ) )
)
```
Why it's wrong: `AVERAGEX` establishes a **row context** over `'Date'[Date]`, but row context **does
not filter** other tables. The inner `SUMX ( 'Inventory', ... )` has no measure reference and no
`CALCULATE`, so **no context transition happens** — on every day of the iteration it scans the *same*
full-period set of `'Inventory'` rows. You get the period total repeated N times, averaged back to…
the period total. It compiles, the numbers look plausible at a single-day cell, and it only betrays
itself at month/period grain.

The fix is to force the current date into the filter context with `CALCULATE` (or by going through a
measure, which carries an implicit `CALCULATE`):
```dax
-- RIGHT: CALCULATE transitions the current date into a filter on 'Inventory'
Avg Inventory Value =
AVERAGEX (
    VALUES ( 'Date'[Date] ),
    CALCULATE ( SUMX ( 'Inventory', 'Inventory'[Units On Hand] * RELATED ( 'Product'[Standard Cost] ) ) )
)
```

A second, related face of the same trap: the **source table** of an inner iterator is itself evaluated
in the outer row context without transition. In
`AVERAGEX ( VALUES ( 'Date'[Year-Month] ), MAXX ( VALUES ( 'Date'[Date] ), [Gross Sales] ) )`, the
inner `VALUES ( 'Date'[Date] )` is **not** scoped to the current month unless the outer row is
transitioned — so it returns every visible day, and the "per-month peak" is really the global peak at
any cell coarser than a month. Wrap the inner expression in `CALCULATE` to scope it:
`AVERAGEX ( VALUES ( 'Date'[Year-Month] ), CALCULATE ( MAXX ( VALUES ( 'Date'[Date] ), [Gross Sales] ) ) )`.

**Rule:** whenever you iterate one table and touch a *different* table (or a coarser/finer set of the
same one) inside, ask out loud "what makes the inner part see only the current row?" If the answer
isn't "a measure reference" or "a `CALCULATE`," you have this bug. And because it produces a
self-consistent-looking wrong answer, **confirm it by actually running the measure** (e.g. an
`EVALUATE` query) rather than trusting the read-through.
