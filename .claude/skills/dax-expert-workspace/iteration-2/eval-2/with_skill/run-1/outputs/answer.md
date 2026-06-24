# Gross Sales 3M Moving Avg

## Suggested name
`Gross Sales 3M Moving Avg`

## Measure

```dax
Gross Sales 3M Moving Avg =
VAR _lastDate =
    MAX ( 'Date'[Date] )
VAR _monthsWindow =                                 -- the 3 months ending in the current month
    DATESINPERIOD ( 'Date'[Date], _lastDate, -3, MONTH )
VAR _monthlyTotals =                                -- one row per month in the window, with that month's gross sales
    ADDCOLUMNS (
        CALCULATETABLE ( VALUES ( 'Date'[Year-Month] ), _monthsWindow ),
        "@MonthlyGross", CALCULATE ( [Gross Sales] )
    )
VAR _monthsWithSales =                              -- only count months that actually have sales (don't always divide by 3)
    FILTER ( _monthlyTotals, NOT ISBLANK ( [@MonthlyGross] ) )
RETURN
    DIVIDE (
        SUMX ( _monthsWithSales, [@MonthlyGross] ),
        COUNTROWS ( _monthsWithSales )
    )
```

## Explanation

The measure builds a virtual table of the three calendar months ending in the currently
displayed month (`DATESINPERIOD ( ..., -3, MONTH )`), grouped by `'Date'[Year-Month]`, and
computes `[Gross Sales]` per month via context transition inside `ADDCOLUMNS`. It then averages
only the months that have non-blank sales, so the divisor is the actual number of months present
(1 for the very first month, 2 for the second, 3 thereafter) rather than always 3. `DIVIDE`
guards against the blank/zero-row case. Because it re-aggregates to month grain internally, it
returns the correct moving average when the visual axis is at month level.

## Assumptions to confirm

- The visual is sliced at **month grain** (e.g. `'Date'[Year-Month]` or Year + Month on the axis).
  The window is anchored on `MAX ( 'Date'[Date] )`, so at a quarter/year total it reflects the last
  3 months of the selected period, and at the grand total it reflects the last 3 months overall —
  expected for a moving-average measure, which is meaningful per-month.
- `'Date'` is the marked Date table with contiguous days, and `'Date'[Year-Month]` uniquely
  identifies a calendar month (format like "2024-03"), as described in the model.
- "Fewer than 3 months of data" is handled by averaging only months with actual sales. If you'd
  instead want to divide by the number of *calendar* months elapsed (counting an in-range month with
  zero sales as a real 0), replace `_monthsWithSales` with `_monthlyTotals` in both the `SUMX` and
  `COUNTROWS`.
- Built on the existing `[Gross Sales]` base measure; no fact columns are re-aggregated directly.
```
