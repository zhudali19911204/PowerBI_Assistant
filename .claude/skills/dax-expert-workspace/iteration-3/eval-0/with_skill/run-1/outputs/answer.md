## Suggested name
`[Avg Monthly Peak Daily Sales]`

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

The inner `MAXX` iterates over each distinct day within a single month and, via the
context transition carried by the `[Gross Sales]` measure reference, evaluates that
day's Gross Sales — returning the highest single-day Gross Sales (the month's peak).
The outer `AVERAGEX` iterates over each month present in the current filter context,
computes that peak for each month, then averages the peaks. Because the iterators
respect the existing filter context, the result automatically reflects whatever
Year / Customer / Product / Store selections are applied, and the average is taken
only over months that actually appear in context.

## Assumptions

- `'Date'` is a marked, contiguous-day Date table related to `'Sales'[Order Date]`,
  and `'Date'[Year-Month]` uniquely identifies a calendar month (e.g. "2024-03"), so
  iterating its `VALUES` enumerates exactly the months in context.
- `[Gross Sales]` is the existing base measure
  `SUMX('Sales','Sales'[Units]*'Sales'[Unit Price]*(1-'Sales'[Discount Pct]))`; the
  measure is reused so any future fix to it propagates here.
- The inner `VALUES('Date'[Date])` is naturally constrained to the current month by
  the outer iterator's context transition, so each `MAXX` only sees that month's days.
- "Average" weights each month equally (a simple mean of the monthly peaks), not a
  day- or sales-weighted average. Months with zero sales would contribute a peak of
  blank/0 only if their days are in context; typically only months with data appear.
```
