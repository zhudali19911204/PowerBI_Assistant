```dax
US Sales Ratio =
VAR _usQuantity =
    CALCULATE ( SUM ( Sales[Quantity] ), 'Customer'[Country] = "United States" )
VAR _usNetAmount =
    CALCULATE ( SUM ( Sales[NetAmount] ), 'Customer'[Country] = "United States" )
RETURN
    DIVIDE ( _usQuantity, _usNetAmount )
```

## What changed and why

- **Replaced `FILTER ( Sales, RELATED ( 'Customer'[Country] ) = "United States" )` with the column predicate `'Customer'[Country] = "United States"`.** *(real performance)* The original forces the Formula Engine to scan the entire `Sales` fact table row by row and resolve a `RELATED` lookup per row. A predicate on the dimension column is pushed down to the Storage Engine as an efficient column filter through the existing `Customer -> Sales` relationship. This is the biggest win, and it ran three times in the original.

- **Computed each aggregation once into a `VAR`.** *(real performance + readability)* The original evaluated the US `NetAmount` total twice (once in the `IF` guard, once as the denominator) and the US `Quantity` total once — each a separate filtered scan. Storing them in `_usQuantity` / `_usNetAmount` evaluates each exactly once and reuses the value, cutting redundant Storage Engine round trips.

- **Replaced the `IF ( denominator > 0, ... / ..., BLANK () )` pattern with `DIVIDE`.** *(safety + performance)* `DIVIDE` returns blank on a zero/blank denominator natively, so the manual `> 0` guard (and its extra evaluation) is unnecessary. `DIVIDE` is also engine-optimized and avoids the error-handling overhead of `/`. Behavior is preserved: when there are no US sales the result is `BLANK ()`, same as before.

- **Behavior preserved.** The business logic (US-only `Quantity` divided by US-only `NetAmount`) is unchanged; only the evaluation path is faster and cleaner. Note the ratio is Quantity / NetAmount (an inverse of average price) — kept exactly as written in case that is intentional.
