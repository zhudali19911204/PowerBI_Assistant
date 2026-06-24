# Net Sales

## Suggested name
`Net Sales`

## Measure

```dax
Net Sales =
VAR ReturnsValue =
    SUMX (
        'Returns',
        VAR OrigDiscountedUnitPrice =
            RELATED ( 'Sales'[Unit Price] ) * ( 1 - RELATED ( 'Sales'[Discount Pct] ) )
        RETURN
            'Returns'[Units Returned] * OrigDiscountedUnitPrice
    )
RETURN
    [Gross Sales] - ReturnsValue
```

## Explanation

`[Net Sales]` is gross sales minus the value of returned units, where each returned
unit is priced at the **same discounted unit price as its original sale line**.

- **Gross side:** reuses the existing `[Gross Sales]` measure
  (`SUMX('Sales', Units * Unit Price * (1 - Discount Pct))`).

- **Returns side:** the `'Returns'` table has only `Units Returned` and no price,
  so we iterate row-by-row over `'Returns'` with `SUMX`. The `Returns[Order Line ID]
  -> Sales[Order Line ID]` relationship is many-to-one (Returns is on the many side),
  so from each return row we can use `RELATED` to pull the original sale line's
  `Unit Price` and `Discount Pct`. The discounted unit price is
  `Unit Price * (1 - Discount Pct)`, matching exactly how `[Gross Sales]` values each
  unit. Multiplying by `Units Returned` gives the value of that return.

- **Net:** subtract the total returns value from gross sales.

### Why this approach
- We do **not** divide a stored sales amount by units (there is no precomputed
  amount column, and division could misvalue partial returns). Instead we
  recompute the unit-level discounted price directly from the source line, so the
  return is valued identically to the sale even when only some units are returned.
- Iterating over `'Returns'` (not `'Sales'`) ensures we count exactly the returned
  units. Because the lookup uses `RELATED` to `'Sales'`, the per-line price is
  always the correct original price regardless of current filter context on price.
- All filter context (Date via `Return Date`, Customer/Product/Store via the active
  relationships propagating through `'Sales'`) is respected naturally. Note that
  in a report sliced by `'Date'`, the gross portion filters on `Order Date` while
  the returns portion filters on `Return Date`, which is the standard accrual
  behavior for this model.
```
