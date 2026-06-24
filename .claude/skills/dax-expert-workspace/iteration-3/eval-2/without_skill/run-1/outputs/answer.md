# Inventory Turnover

## Suggested name
`[Inventory Turnover]`

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
        // average over days that actually have a snapshot in the period
        CALCULATETABLE (
            VALUES ( 'Date'[Date] ),
            'Inventory'
        ),
        // a single day's total inventory value, summed across products/stores
        SUMX (
            'Inventory',
            'Inventory'[Units On Hand] * RELATED ( 'Product'[Standard Cost] )
        )
    )
RETURN
    DIVIDE ( _COGS, _AvgInventoryValue )
```

## Explanation

- **COGS (numerator):** `SUMX` over `'Sales'` multiplies each row's `Units` by the product's
  `Standard Cost` (pulled via `RELATED` across the active Product relationship). This evaluates in
  the current filter context, so it is the COGS for whatever period/selection is on the visual.
- **Average inventory value (denominator):** Because `'Inventory'` is a daily snapshot,
  `AVERAGEX` iterates **one row per date**. For each date, context transition restricts
  `'Inventory'` to that day and the inner `SUMX` computes that day's total inventory value
  (Units On Hand x Standard Cost, summed across all products and stores). `AVERAGEX` then takes
  the **average across the days** — not a sum — which is exactly what the definition requires for a
  semi-additive snapshot.
- **Day set:** The iterator runs over `CALCULATETABLE ( VALUES ( 'Date'[Date] ), 'Inventory' )`,
  i.e. only the dates that have at least one inventory snapshot row within the current period. This
  prevents days with no snapshot from being counted as zero-value days and dragging the average down.
- **`DIVIDE`** guards against divide-by-zero (returns blank instead of erroring) when there is no
  inventory in the period.

## Assumptions to confirm

- A marked, contiguous `'Date'` table named `'Date'` exists (it does, per the model), and the
  active relationships `'Date'[Date] -> Sales[Order Date]` / `Inventory[Snapshot Date]` and
  `'Product'[Product ID] -> Sales[Product ID]` / `Inventory[Product ID]` are in place.
- "Days in the period" is interpreted as the snapshot dates present within the current filter
  context. If instead you want to average over *every* calendar day in the period (treating
  snapshot-less days as 0), replace the iterated table with `VALUES ( 'Date'[Date] )`.
