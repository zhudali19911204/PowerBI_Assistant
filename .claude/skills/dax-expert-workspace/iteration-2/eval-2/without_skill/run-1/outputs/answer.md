# Gross Sales 3M Moving Avg

## Suggested name
`Gross Sales 3M Moving Avg`

## Measure

```dax
Gross Sales 3M Moving Avg =
VAR CurrentDate =
    MAX ( 'Date'[Date] )
VAR Window =
    DATESINPERIOD ( 'Date'[Date], CurrentDate, -3, MONTH )
VAR MonthlyTotals =
    ADDCOLUMNS (
        SUMMARIZE (
            CALCULATETABLE ( 'Sales', Window ),
            'Date'[Year],
            'Date'[Month Number]
        ),
        "@MonthSales", [Gross Sales]
    )
VAR MonthsWithData =
    COUNTROWS ( FILTER ( MonthlyTotals, NOT ISBLANK ( [@MonthSales] ) ) )
VAR TotalSales =
    SUMX ( MonthlyTotals, [@MonthSales] )
RESULT =
    DIVIDE ( TotalSales, MonthsWithData )
```

## Explanation

- **Window definition.** `DATESINPERIOD ( 'Date'[Date], MAX('Date'[Date]), -3, MONTH )` returns the set of dates covering the current month plus the previous two months. Because `'Date'` is a marked, contiguous Date table, this correctly walks back across month/year boundaries (e.g. Jan -> Nov of prior year).

- **Per-month aggregation.** The average must be over **monthly totals**, not over individual fact rows. `SUMMARIZE` (grouped by `Year` + `Month Number`, which uniquely identify a calendar month) produces one row per month in the window, and `ADDCOLUMNS` evaluates `[Gross Sales]` in each month's context. `SUMX` then sums those three (or fewer) monthly totals.

- **Correct display at month level.** Using `MAX('Date'[Date])` as the anchor means the measure recomputes the trailing window for whichever month is on the visual, so each month shows its own correct 3-month average. The window is built from the Date table independent of the current month filter, so the prior two months are pulled in even though they are filtered out of the visual row.

- **Partial windows (fewer than 3 months).** The denominator is `MonthsWithData` — the count of months in the window that actually have sales — not a hard-coded 3. So the very first month divides by 1, the second by 2, and from the third month onward by 3. Filtering on `NOT ISBLANK([@MonthSales])` also avoids counting empty months at the start of the data, so the early months are not understated. `DIVIDE` guards against a blank/zero denominator.

- **Result.** At month granularity this yields the average of the current month and up to two preceding months of `[Gross Sales]`, sized to the months of data available.
