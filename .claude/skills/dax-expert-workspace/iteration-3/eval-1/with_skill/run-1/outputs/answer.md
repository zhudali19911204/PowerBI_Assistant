# Cumulative Sales % (Pareto / 80-20 curve)

## Suggested name
`Cumulative Sales %`

## Measure

```dax
Cumulative Sales % =
VAR _CurrentGross =
    [Gross Sales]
-- The set of products that are visible after external slicers (Year, Region, Category, ...),
-- but ignoring the current row of 'Product'[Product Name], each tagged with its own Gross Sales.
VAR _ProductsWithSales =
    ADDCOLUMNS (
        ALLSELECTED ( 'Product'[Product Name] ),
        "@Gross", [Gross Sales]
    )
-- Grand total of Gross Sales across all visible products (the Pareto denominator).
VAR _GrandTotal =
    SUMX ( _ProductsWithSales, [@Gross] )
-- Running total: every product whose Gross Sales is >= the current product's Gross Sales
-- (i.e. ranked equal-or-higher when sorted descending), accumulated.
VAR _CumulativeTotal =
    SUMX (
        FILTER (
            _ProductsWithSales,
            [@Gross] >= _CurrentGross
        ),
        [@Gross]
    )
RETURN
    IF (
        NOT ISBLANK ( _CurrentGross ),
        DIVIDE ( _CumulativeTotal, _GrandTotal )
    )
```

## Explanation

For the product on the current axis row, the measure captures its `[Gross Sales]`, builds the
slicer-respecting list of all visible products (`ALLSELECTED('Product'[Product Name])`) with each
product's own Gross Sales, then accumulates the Gross Sales of every product selling at least as much
as the current one. Dividing that running total by the grand total of all visible products gives the
cumulative (Pareto) share, so plotting `[Cumulative Sales %]` against `'Product'[Product Name]` sorted
by `[Gross Sales]` descending lets you read off the products that make up the top 80%. Because the
population comes from `ALLSELECTED`, external slicers on Year, Region, Category, etc. flow through to
both the running total and the denominator, while the current product-row filter is removed so the
accumulation can see all peers.

## Assumptions

- `[Gross Sales]` is the existing base measure as defined in the model; the measure builds on it
  rather than re-deriving the sum.
- Used in a visual with `'Product'[Product Name]` on the axis, sorted by `[Gross Sales]` descending.
  The result is rank-order independent (it compares Gross Sales values), so it is correct regardless
  of the visual's sort, but the Pareto curve only reads cleanly when sorted descending.
- "Visible products" is defined at the `'Product'[Product Name]` grain. If several distinct products
  share an identical Product Name, they are treated as one bucket; if names must stay distinct, swap
  the grain to `'Product'[Product ID]` (or add it) in both `ALLSELECTED` and the axis.
- Ties in Gross Sales: products with exactly equal Gross Sales are all included in each other's
  running total, so tied products report the same cumulative %. This is the standard, defensible
  Pareto behavior.
- `IF ( NOT ISBLANK ( _CurrentGross ), ... )` blanks out products with no sales in the current filter
  context so they don't flat-line the curve at 100%; remove it if you want every product plotted.
