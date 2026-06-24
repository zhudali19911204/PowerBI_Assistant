# % of Category Sales

## Suggested name
`% of Category Sales`

## Measure

```dax
% of Category Sales =
DIVIDE (
    [Total Sales],
    CALCULATE (
        [Total Sales],
        REMOVEFILTERS ( 'Product'[Product], 'Product'[Subcategory] )
    )
)
```

## Explanation

- **Numerator** `[Total Sales]` is the sales for the current cell — i.e. for the
  specific product in context, already filtered by every slicer the user has
  applied (year, country, color, etc.).

- **Denominator** recomputes `[Total Sales]` but with `REMOVEFILTERS` clearing
  only the columns that distinguish products *within* a category — `'Product'[Product]`
  (and `'Product'[Subcategory]`, since a subcategory also narrows below the
  category level). The `'Product'[Category]` filter is deliberately **kept**, so
  the denominator is the total of the product's own category.

- Because we only remove the product-level filters and leave everything else
  untouched, the denominator still honors all other slicers (Date[Year],
  Customer[Country], Product[Color], …). A year/country slicer reduces both the
  numerator and the denominator consistently, so the percentage reflects "this
  product's share of its category, within the current slicer selection."

- `DIVIDE` is used instead of `/` so a category total of zero or blank returns
  BLANK() rather than a divide-by-zero error.

### Notes / alternatives

- If you put this measure in a matrix sliced **by category** (category on rows
  or as a slicer), keeping the `Category` filter is exactly what you want: each
  product is measured against its visible category total.
- If you instead want each product compared to its category total *regardless*
  of whether a category is also being filtered as a grouping, the same formula
  still works because removing `[Product]`/`[Subcategory]` collapses to the
  category grain while preserving the category context.
- This intentionally does **not** use `ALLEXCEPT` or `ALL('Product')`, which
  would either wipe the slicer filters or require re-listing every external
  column. Removing just the product/subcategory columns is the minimal,
  slicer-safe approach.
- If returns should be excluded, the model's `[Total Sales]` would need to
  account for `Sales[ReturnFlag]`; as given it sums all `NetAmount`, and this
  measure inherits whatever `[Total Sales]` does.
