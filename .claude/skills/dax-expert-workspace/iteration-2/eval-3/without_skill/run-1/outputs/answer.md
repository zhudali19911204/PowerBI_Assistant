# Closing Inventory (Units On Hand at last date of period)

## Suggested name
`Closing Inventory`

## Measure

```dax
Closing Inventory =
CALCULATE (
    SUM ( Inventory[Units On Hand] ),
    LASTNONBLANKVALUE (
        'Date'[Date],
        CALCULATE ( SUM ( Inventory[Units On Hand] ) )
    )
)
```

### Simpler alternative (if every product/store has a snapshot on the last calendar day of the period)

```dax
Closing Inventory =
CALCULATE (
    SUM ( Inventory[Units On Hand] ),
    LASTDATE ( 'Date'[Date] )
)
```

## Explanation

The goal is a semi-additive "closing balance": the inventory is a daily snapshot,
so summing `Units On Hand` over a multi-day period would double- (or N-times-) count
the same stock once per day. Instead we want the value at only the **last day** of
whatever period is in filter context, but still summed across all products and stores
in context.

- `SUM ( Inventory[Units On Hand] )` aggregates additively across the **Product** and
  **Store** dimensions (and any other non-date filters) — this is correct, because
  on a single day units across different products/stores genuinely add up.
- The time dimension is the non-additive one. We collapse the date filter down to a
  single day before summing:
  - **Recommended version** uses `LASTNONBLANKVALUE ( 'Date'[Date], ... )`, which
    returns the last date in the current context that actually has inventory data.
    This is robust when the final calendar day of a month/period has no snapshot
    (e.g. month-end falls on a non-business day, or data simply hasn't loaded for the
    last day yet). It picks the most recent day that has a balance.
  - The **simpler `LASTDATE`** version returns the maximum date in context regardless
    of whether a snapshot exists on it. It is cleaner and faster, but returns blank
    for a product/store/day combination that has no row on the exact last calendar
    day. Use it only if you are confident every entity is snapshotted on the period's
    final day.

Because `'Date'` is a marked Date table with an active relationship to
`Inventory[Snapshot Date]`, both `LASTDATE` and `LASTNONBLANKVALUE` operate over the
dates currently visible (a day, month, quarter, year, or the grand total), so the
measure automatically yields the correct closing balance at every level of a report
without double-counting across days.
