# Year-over-Year Sales Growth %

## Suggested measure name
`Sales YoY %`

## Measure

```dax
Sales YoY % =
VAR _currentSales =
    [Total Sales]
VAR _priorYearSales =
    CALCULATE (
        [Total Sales],
        SAMEPERIODLASTYEAR ( 'Date'[Date] )
    )
RETURN
    DIVIDE (
        _currentSales - _priorYearSales,
        _priorYearSales
    )
```

## Explanation

The measure freezes the current filter context's sales into `_currentSales` (reusing the existing `[Total Sales]` base measure), then computes the same period one year earlier into `_priorYearSales` by using `CALCULATE` with `SAMEPERIODLASTYEAR` to shift the Date filter back 12 months. It returns the relative growth — `(this year - last year) / last year` — via `DIVIDE`, so a result of `0.10` means sales grew 10% versus the same period last year. Because the comparison is built on `[Total Sales]` and a shifted Date filter, it works correctly at any grain the visual exposes (whole year, quarter, month, or a date-range slicer), comparing each period against its matching period a year prior.

Format the result as a percentage in the visual (or wrap in `FORMAT(..., "0.0%")` only if you need a text label, not a numeric value).

## Assumptions

- The model has a Date dimension named `'Date'` that is **marked as a Date table** with one contiguous row per day covering the data range, and `'Date'[Date]` is the date column — required for `SAMEPERIODLASTYEAR` to behave reliably. (Both conditions are stated in the provided model.)
- Builds on the existing `[Total Sales] = SUM ( Sales[NetAmount] )` measure, so it includes all sales rows in context. If you intend to **exclude returns** (`Sales[ReturnFlag] = 1`), that exclusion must be handled in `[Total Sales]` (or a dedicated net-of-returns base measure) rather than here.
- `DIVIDE` returns BLANK when there are no prior-year sales (e.g., the first year of data), avoiding divide-by-zero errors; pass a third argument to `DIVIDE` if you'd prefer a different fallback.
- The active relationship `Sales[OrderDateKey] -> 'Date'[DateKey]` is the date context used, so growth is measured by order date.
