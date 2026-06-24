# % of Category Sales

## Suggested name
`Sales % of Category`

## Measure

```dax
Sales % of Category =
VAR _productSales = [Total Sales]
VAR _categorySales =
    CALCULATE (
        [Total Sales],
        REMOVEFILTERS (
            'Product'[Product],
            'Product'[Subcategory],
            'Product'[Color]
        )
    )
RETURN
    DIVIDE ( _productSales, _categorySales )
```

## Explanation

- **Numerator** `_productSales` is just `[Total Sales]` in the current filter context, so it already
  reflects the row's product and every external slicer (Year, Country, etc.).
- **Denominator** `_categorySales` recomputes `[Total Sales]` after `REMOVEFILTERS` clears only the
  *within-category* Product attributes — `'Product'[Product]`, `'Product'[Subcategory]`, and
  `'Product'[Color]`. Because `'Product'[Category]` is **not** removed, the filter on the current
  category survives, giving the total for that category. Critically, filters coming from other tables
  (`'Date'[Year]`, `'Customer'[Country]`, etc.) are untouched, so the share still respects all slicers.
- `DIVIDE` returns blank instead of erroring when a category has zero/blank sales in the current
  context.

## Why clear specific columns instead of the whole `'Product'` table

`REMOVEFILTERS('Product')` would also wipe the `Category` filter, turning the denominator into the
grand total across *all* categories — i.e. "% of all products," not "% of its own category." Listing
only the sub-Category columns keeps `Category` (and any custom grouping above it you might add) in
force. If you want the share to also ignore a Subcategory slicer the user applied, keep removing
Subcategory as above; if instead Subcategory should be respected as a grouping level, drop it from the
`REMOVEFILTERS` list.

## Assumptions to confirm

- The product hierarchy columns are `'Product'[Category]` > `'Product'[Subcategory]` > `'Product'[Product]`,
  with `'Product'[Color]` as an additional descriptive attribute (matches the supplied model).
- `[Total Sales] = SUM ( Sales[NetAmount] )` is the intended sales measure (returns are not excluded,
  consistent with the existing base measure; if returns should be excluded, adjust `[Total Sales]`).
