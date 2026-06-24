## Suggested name

`Closing Inventory`

## Measure

```dax
Closing Inventory =
CALCULATE (
    SUM ( Inventory[Units On Hand] ),
    LASTNONBLANK (
        'Date'[Date],
        CALCULATE ( COUNTROWS ( Inventory ) )
    )
)
```

## Explanation

This is a classic semi-additive (snapshot / balance) measure: Units On Hand is additive across products and stores, but it must **not** be added up across the days of a period — that would count the same stock many times. The measure therefore collapses the time dimension to a single day before summing.

`LASTNONBLANK ( 'Date'[Date], CALCULATE ( COUNTROWS ( Inventory ) ) )` walks the dates currently in filter context from latest to earliest and returns the last date that actually has at least one Inventory row. `CALCULATE` then restricts the filter context to that one closing date, and `SUM ( Inventory[Units On Hand] )` adds the on-hand units across exactly the products and stores still in context for that date. Because only one date survives, days are never double-counted, while products, stores, categories, and regions remain fully additive.

The behavior adapts to whatever period is in context: at a month it returns the last day of that month, at a year the last day of that year, and at the grand total the last date overall — always the closing balance.

## Assumptions

- `'Date'` is a marked Date table with contiguous daily rows (stated in the model), so "last date of the current period" is well defined and time intelligence over `'Date'[Date]` is reliable.
- The active relationship `Inventory[Snapshot Date] -> 'Date'[Date]` is used; filters on `'Date'` propagate to `Inventory`.
- `LASTNONBLANK` (rather than a plain `LASTDATE`) is used so that if the very last calendar day of a period has no snapshot rows, the measure falls back to the most recent day that does — a more robust closing balance for a daily snapshot.
- The snapshot grain is one row per date/product/store, so summing `Units On Hand` on a single date does not itself double-count.
