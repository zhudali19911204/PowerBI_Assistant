# Net Sales

## Measure

```dax
Net Sales =
VAR _returnValue =
    SUMX (
        'Returns',
        'Returns'[Units Returned]
            * RELATED ( 'Sales'[Unit Price] )
            * ( 1 - RELATED ( 'Sales'[Discount Pct] ) )
    )
RETURN
    [Gross Sales] - _returnValue
```

## Suggested name

`Net Sales`

## Explanation

`[Gross Sales]` already gives discounted gross revenue for the rows visible in the current filter
context. The `SUMX` over `'Returns'` then values every returned line: because `Returns[Order Line ID]`
has a many-to-one relationship to `'Sales'`, `RELATED` reaches up from each return row to its single
parent sale line and pulls that line's `Unit Price` and `Discount Pct`. Multiplying
`Units Returned * Unit Price * (1 - Discount Pct)` values each returned unit at exactly the same
discounted unit price as the original sale, and subtracting that total from gross sales yields net
sales. The Returns table has no price column of its own, which is why the price must be borrowed from
the related Sales line.

## Assumptions

- The active `Returns[Order Line ID] -> 'Sales'[Order Line ID]` (many-to-one) relationship is in place
  so that `RELATED('Sales'[...])` resolves to the originating sale line. (Confirmed present in the
  supplied model.)
- "Discounted unit price" means `Unit Price * (1 - Discount Pct)`, the same per-unit revenue basis used
  by the existing `[Gross Sales]` measure.
- Returns are netted against gross sales within whatever filter context the measure is evaluated in.
  Returns are filtered by their own dimensions/date: `Customer`, `Product`, and `Store` reach a return
  row through its parent `Sales` line (relationship expansion), while a date filter applies to returns
  via `Returns[Return Date]` (the return's own date), not the original `Order Date`. If the requirement
  is instead to net returns based on the original order's attributes/date, the measure would need to be
  reframed to iterate Sales and pull related returns — confirm which timing/grain is intended.
- Each sale has at most one return (per the model note), so no double counting occurs; if a sale could
  have multiple returns, this still sums them correctly.
```
