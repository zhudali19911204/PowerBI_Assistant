## Optimized Measure

```dax
US Sales Ratio =
VAR USNetAmount =
    CALCULATE (
        SUM ( Sales[NetAmount] ),
        'Customer'[Country] = "United States"
    )
VAR USQuantity =
    CALCULATE (
        SUM ( Sales[Quantity] ),
        'Customer'[Country] = "United States"
    )
RETURN
    IF (
        USNetAmount > 0,
        DIVIDE ( USQuantity, USNetAmount )
    )
```

## What changed and why

1. **Replaced `FILTER ( Sales, RELATED ( 'Customer'[Country] ) = "United States" )` with a column predicate `'Customer'[Country] = "United States"`.**
   The original filter forces a row-by-row iteration over the entire `Sales` fact table and resolves `RELATED` for every row, which prevents the storage engine from applying an efficient filter and is the main cause of the slowness. Filtering directly on the `'Customer'` dimension column lets the engine push the filter through the active one-to-many relationship and evaluate it as a fast, internally-optimized scan. It also produces a compact dimension-table filter context instead of a large `Sales` row filter.

2. **Computed each aggregate once with variables instead of three repeated `CALCULATE` calls.**
   The original evaluated the US `NetAmount` sum twice (once in the `IF` condition, once in the denominator) plus the US `Quantity` sum once — three filtered context transitions. Storing `USNetAmount` and `USQuantity` in `VAR`s evaluates each exactly once and reuses the results, cutting redundant work.

3. **Used `DIVIDE` instead of the `/` operator.**
   `DIVIDE` handles divide-by-zero safely and is the idiomatic guard. The `IF ( USNetAmount > 0, ... )` is kept to preserve the original behavior of returning `BLANK ()` when there are no US net sales (the omitted third argument of `IF` defaults to `BLANK ()`, so the explicit `BLANK ()` is no longer needed).

Note: the business logic (Quantity divided by NetAmount, gated on NetAmount > 0) is preserved exactly as written in the original measure.
