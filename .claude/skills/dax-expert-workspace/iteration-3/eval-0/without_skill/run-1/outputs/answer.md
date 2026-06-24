# Avg Monthly Peak Daily Sales

## Suggested name
`Avg Monthly Peak Daily Sales`

## Measure

```dax
Avg Monthly Peak Daily Sales =
AVERAGEX (
    VALUES ( 'Date'[Year-Month] ),
    MAXX (
        VALUES ( 'Date'[Date] ),
        [Gross Sales]
    )
)
```

## Explanation

This is a nested iteration with two context transitions:

1. The outer `AVERAGEX` iterates the distinct months currently in the filter
   context (`VALUES('Date'[Year-Month])`). Each iteration places one
   `Year-Month` into filter context (context transition from the `[Gross Sales]`
   evaluation inside), so the inner expression is scoped to that single month.
2. For each month, the inner `MAXX` iterates the distinct days of that month
   (`VALUES('Date'[Date])` — already restricted to the current month by the
   outer context) and evaluates `[Gross Sales]` for each day. Referencing the
   measure triggers context transition, so each day's value is that day's Gross
   Sales. `MAXX` returns the single highest daily Gross Sales = the month's peak
   day.
3. `AVERAGEX` then averages those per-month peak values across the months in
   context.

Because everything is driven by `VALUES`, the measure respects whatever is in
the current filter context: at a single-month grain it returns that month's peak
day; across a year it averages the 12 monthly peaks; with a Store/Product slicer
applied, peaks are computed on the filtered Gross Sales.

## Assumptions to confirm

- A marked Date table named `'Date'` exists with contiguous days, and
  `'Date'[Year-Month]` uniquely identifies each calendar month (it does, given
  the `"YYYY-MM"` format), so `VALUES('Date'[Year-Month])` correctly enumerates
  months even across year boundaries.
- `'Date'[Date]` is at day grain, so `VALUES('Date'[Date])` yields one row per
  calendar day. Days with no sales contribute a blank `[Gross Sales]`, which
  `MAXX` ignores and never becomes a spurious peak.
- "Peak daily sales" is measured as total Gross Sales per calendar day (summed
  across all orders that day), per the existing `[Gross Sales]` definition.
```
