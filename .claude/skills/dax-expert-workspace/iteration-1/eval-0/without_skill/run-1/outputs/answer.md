# Year-over-Year Sales Growth %

**Suggested measure name:** `Sales YoY %`

```dax
Sales YoY % =
VAR _CurrentSales = [Total Sales]
VAR _PriorYearSales =
    CALCULATE (
        [Total Sales],
        SAMEPERIODLASTYEAR ( 'Date'[Date] )
    )
VAR _Result =
    DIVIDE (
        _CurrentSales - _PriorYearSales,
        _PriorYearSales
    )
RETURN
    _Result
```

## Explanation

This measure compares sales in the current filter context against the same period one year earlier and returns the growth as a percentage.

- **`_CurrentSales`** captures `[Total Sales]` for whatever period the user has filtered (a year, quarter, month, or any date range on the report).
- **`_PriorYearSales`** uses `CALCULATE` with `SAMEPERIODLASTYEAR ( 'Date'[Date] )` to shift the current date selection back exactly one year and re-evaluate `[Total Sales]`. `SAMEPERIODLASTYEAR` requires a marked Date table with a contiguous, day-grain date column — the model's `'Date'` table satisfies this, so we point it at `'Date'[Date]`.
- **`DIVIDE`** computes `(This Year − Last Year) / Last Year`. Using `DIVIDE` (rather than the `/` operator) safely returns a blank instead of an error when there is no prior-year value (e.g., the first year of data), avoiding divide-by-zero issues.

The result is a ratio; format the measure as a **Percentage** in Power BI so values display as e.g. `12.5%`. The measure is fully dynamic and respects slicers and any date level on rows/columns because it builds on the existing `[Total Sales]` measure and the active `Sales[OrderDateKey] -> 'Date'[DateKey]` relationship.

**Optional:** If you want a clean blank instead of a misleading 100%+ figure when there is no prior-year data, you can guard it:

```dax
Sales YoY % =
VAR _CurrentSales = [Total Sales]
VAR _PriorYearSales =
    CALCULATE ( [Total Sales], SAMEPERIODLASTYEAR ( 'Date'[Date] ) )
RETURN
    IF (
        NOT ISBLANK ( _PriorYearSales ),
        DIVIDE ( _CurrentSales - _PriorYearSales, _PriorYearSales )
    )
```
