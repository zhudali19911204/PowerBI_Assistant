## Suggested name

`Inventory Turnover`

## Measure

```dax
Inventory Turnover =
VAR _COGS =
    SUMX (
        'Sales',
        'Sales'[Units] * RELATED ( 'Product'[Standard Cost] )
    )
VAR _AvgInventoryValue =
    AVERAGEX (
        VALUES ( 'Date'[Date] ),
        SUMX (
            'Inventory',
            'Inventory'[Units On Hand] * RELATED ( 'Product'[Standard Cost] )
        )
    )
RETURN
    DIVIDE ( _COGS, _AvgInventoryValue )
```

## Explanation

`_COGS` values every unit sold in the current filter context at its product's Standard Cost (pulled from `'Product'` via the active relationship using `RELATED`), and sums them. `_AvgInventoryValue` iterates the **distinct dates in the period** (`VALUES('Date'[Date])`); for each day, context transition from the iterator filters `'Inventory'` to that single snapshot date, where the inner `SUMX` computes that day's total inventory value across every product/store. `AVERAGEX` then takes the mean of those daily values — averaging over days, never summing them. `DIVIDE` returns the turnover and yields blank (not an error) if average inventory is zero.

## Assumptions

- A marked, contiguous `'Date'` table exists, with the active relationships `Sales[Order Date] -> 'Date'[Date]` and `Inventory[Snapshot Date] -> 'Date'[Date]` (the Date table drives the "days in the period").
- `VALUES('Date'[Date])` iterates over the dates currently in the filter context. If you want the average to span only days that actually have inventory snapshots (rather than every calendar day in the period, including days with no rows that would contribute 0), replace `VALUES('Date'[Date])` with a date set restricted to snapshot dates, e.g. `CALCULATETABLE ( VALUES ( 'Date'[Date] ), 'Inventory' )`. As written, calendar days in the period with no inventory rows contribute a value of 0 to the average; this is generally the desired "average over the days in the period" behavior for a daily snapshot that should have a row every day.
- `RELATED('Product'[Standard Cost])` resolves through the many-to-one relationships on `Product ID` for both `'Sales'` and `'Inventory'`.
- COGS uses `Sales[Units]` valued at Standard Cost (not Unit Price / not the existing `[Gross Sales]` revenue measure), per the task definition.
