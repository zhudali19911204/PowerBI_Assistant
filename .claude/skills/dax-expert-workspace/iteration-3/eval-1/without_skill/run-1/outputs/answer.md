# Cumulative Sales % (Pareto curve)

## Suggested measure name
`Cumulative Sales %`

## DAX

```dax
Cumulative Sales % =
VAR CurrentProductSales = [Gross Sales]
VAR AllProducts =
    -- Product-level Gross Sales, keeping all external slicers (Year, Region,
    -- Category, ...) but removing any filter on Product Name so we can rank
    -- the full visible product set against the current row.
    CALCULATETABLE (
        ADDCOLUMNS (
            VALUES ( 'Product'[Product Name] ),
            "@Sales", [Gross Sales]
        ),
        REMOVEFILTERS ( 'Product'[Product Name] )
    )
VAR CumulativeSales =
    -- Sum of Gross Sales for every product whose sales are >= the current
    -- product's sales (i.e. ranked at or above it, descending order).
    SUMX (
        FILTER ( AllProducts, [@Sales] >= CurrentProductSales ),
        [@Sales]
    )
VAR TotalSales =
    SUMX ( AllProducts, [@Sales] )
RETURN
    DIVIDE ( CumulativeSales, TotalSales )
```

## Explanation

The measure builds a running cumulative share of total Gross Sales after ranking
products from highest to lowest sales — the standard Pareto / 80-20 curve.

How it works:

1. **`CurrentProductSales`** captures the Gross Sales of the product on the
   current row of the visual (the row where the measure is being evaluated).

2. **`AllProducts`** uses `CALCULATETABLE` with
   `REMOVEFILTERS('Product'[Product Name])` to materialize a virtual table of
   every product currently visible, each with its own Gross Sales (`@Sales`).
   Removing the Product Name filter is essential: it lets the current row "see"
   all sibling products so it can compare ranks. Crucially, only the Product
   Name filter is stripped — every other filter (Year, Region, Category, Store,
   any external slicer) stays in force, so the curve always reflects the current
   slicer selection.

3. **`CumulativeSales`** sums the Gross Sales of all products whose sales are
   greater than or equal to the current product's sales. Because higher-selling
   products rank first, this is exactly the running total "from the top down"
   to the current product.

4. **`TotalSales`** is the grand total of Gross Sales across all visible products.

5. **`DIVIDE`** returns the cumulative figure as a fraction of the total
   (format the measure as a percentage). The top product returns its own share,
   and the value climbs to 100% at the lowest-selling product — drop a line at
   80% to read off the vital-few products.

Notes / good practice:

- Format the measure as **Percentage**. Reading it with
  `'Product'[Product Name]` on the axis sorted by `[Gross Sales]` descending
  gives the proper Pareto shape.
- A defensive tie-breaker is not strictly required for the cumulative concept,
  but if two products have identical Gross Sales they will report the same
  cumulative %. If you need a strictly monotonic curve under ties, extend the
  `FILTER` comparison with a deterministic secondary key, e.g.
  `[@Sales] > CurrentProductSales || ([@Sales] = CurrentProductSales && ...)`.
- The measure relies only on the existing `[Gross Sales]` measure and the
  `'Product'[Product Name]` column, so it stays valid as long as those exist.
```
