# DAX performance: the engines, and an anti-pattern → fix catalog

> Distilled in original wording from *The Definitive Guide to DAX* (engine internals & optimization
> chapters), SQLBI articles, and daxpatterns.com. No source text reproduced. Use when asked to
> optimize a measure, or to explain why one is slow.

## Table of contents
1. The two engines (why this is the whole game)
2. How to think about a slow measure
3. Anti-pattern → fix catalog
4. Cardinality, data types, and the model
5. Honesty rule

---

## 1. The two engines (why this is the whole game)
Every DAX query is split between two engines:

- **Storage Engine (SE / VertiPaq)** — a compressed, columnar, multi-threaded cache. It is *fast* and
  does simple, set-based work: scan a column, filter, group, sum/count. It cannot do complex
  iterative logic.
- **Formula Engine (FE)** — single-threaded, does everything the SE can't (complex iteration, joins
  it can't push down, cell-by-cell logic). It is *slower* and is the usual bottleneck.

**The optimization goal is almost always: push more work into the SE and out of the FE**, and reduce
the number of SE queries and the size of the data materialized between them. A measure is slow usually
because it forces the FE to iterate over large intermediate tables, or because it triggers many small
SE calls (a "CallbackDataID" when the FE has to call back into the SE row by row).

You don't need a query plan to apply the catalog below — these patterns reliably move work the right
direction. For genuinely hard cases, measure with DAX Studio (server timings: SE vs FE time, rows
materialized) rather than guessing.

## 2. How to think about a slow measure
Ask, in order:
1. **What does it iterate, and how big is that table?** Iterating a fact table with a measure
   reference (context transition) inside is the #1 cost.
2. **Is there a context transition inside an iterator?** Each iteration becomes an SE query unless the
   engine can fuse it. Can you reformulate without per-row transition?
3. **Is a whole table being filtered** where a column predicate would do?
4. **Is the same subexpression computed repeatedly** instead of stored in a `VAR`?
5. **Is anything materializing a big intermediate table** to the FE (large `FILTER`, `ADDCOLUMNS` over
   the fact table, cross joins)?

## 3. Anti-pattern → fix catalog
Each entry: the smell, why it hurts, the fix.

### A. `FILTER` over a whole (large) table as a CALCULATE filter
```dax
-- slow
CALCULATE ( [Total Sales], FILTER ( Sales, Sales[Region] = "East" ) )
-- fast: column predicate → efficient SE filter
CALCULATE ( [Total Sales], Sales[Region] = "East" )
```
The first scans the fact table row by row in the FE; the second is a pushed-down SE filter. If you do
need `FILTER`, filter the smallest possible table (`FILTER ( VALUES ( Sales[Region] ), ... )`).

### B. `/` instead of `DIVIDE`
Not just safety — `DIVIDE` is optimized and avoids error-handling overhead. Always use it for ratios.

### C. Repeated subexpressions (no variables)
```dax
-- recomputes [Total Sales] three times, each a context transition / SE round trip
IF ( [Total Sales] > 0, [Total Sales] * [Total Sales] , BLANK () )
-- compute once
VAR _s = [Total Sales]
RETURN IF ( _s > 0, _s * _s, BLANK () )
```

### D. Context transition inside a big iterator
```dax
-- slow: per-row context transition over the whole fact table
SUMX ( Sales, [Total Sales] )
-- usually you meant a plain aggregation:
SUMX ( Sales, Sales[Quantity] * Sales[Net Price] )
```
Reserve `SUMX(table, [measure])` for when you genuinely need the measure re-evaluated per row of a
*small* table (e.g., per category), not per fact row.

### E. `COUNTROWS ( FILTER ( T, cond ) )` for a simple count
```dax
-- slow
COUNTROWS ( FILTER ( Sales, Sales[Quantity] > 0 ) )
-- fast
CALCULATE ( COUNTROWS ( Sales ), Sales[Quantity] > 0 )
```

### F. Unnecessary calculated columns
A calculated column materializes for every row at refresh and consumes memory, often with poor
compression. If the value is only needed in aggregation, make it a measure. Keep calculated columns
for keys, relationship columns, and slicer/axis attributes that must be physical.

### G. `FORMAT` (or other text) where a number is expected
`FORMAT` returns **text**, which kills further numeric aggregation and forces the FE. Keep measures
numeric; apply formatting in the visual or via a format string, not by converting to text mid-calc.

### H. Redundant / nested `CALCULATE`
Collapse stacked `CALCULATE`s and lift invariant filters out of iterators. Each `CALCULATE` is a
context change with cost; don't pay for it more than once.

### I. Bidirectional / many-to-many filtering left on model-wide
Bidirectional relationships make many queries slower and can introduce ambiguity. Prefer local
`CROSSFILTER` for the one calculation that needs it.

### J. `IF` branches that each re-trigger expensive evaluations
Compute the expensive parts into `VAR`s first, then branch on the variables, so a branch never causes
a recomputation.

## 4. Cardinality, data types, and the model
Performance starts in the model, not the measure:
- **Lower column cardinality compresses better and scans faster.** High-cardinality columns (free-text,
  precise datetimes, GUIDs) are the enemy. **Split datetime into a date key + a time-of-day column**;
  drop unused decimals.
- **Prefer integer keys** for relationships over text keys.
- **Remove unused columns** — VertiPaq pays for every column, used or not.
- **Star schema beats snowflake/flat** for the engine: narrow fact, well-keyed dimensions. (This is
  also why the project's modeling phase matters for DAX speed.)

## 5. Honesty rule
When you optimize, distinguish **correctness/safety** fixes (e.g., `/` → `DIVIDE`), **readability**
fixes (variables, formatting), and **real performance** fixes (removing FE materialization, killing
context transition in big iterators). Don't claim a speedup you can't justify. If a rewrite is only
cleaner, say "same speed, clearer". If you can, confirm with DAX Studio server timings rather than
asserting.
