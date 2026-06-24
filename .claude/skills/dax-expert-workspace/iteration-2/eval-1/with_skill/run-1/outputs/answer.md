# Customers Above Avg

## Measure

```dax
Customers Above Avg =
VAR _customers =
    ADDCOLUMNS (
        VALUES ( 'Customer'[Customer ID] ),
        "@CustGross", [Gross Sales]
    )
VAR _avgGross =
    AVERAGEX ( _customers, [@CustGross] )
RETURN
    COUNTROWS (
        FILTER (
            _customers,
            [@CustGross] > _avgGross
        )
    )
```

## Suggested name
`Customers Above Avg`

## Explanation
For the customers visible in the current filter context, the measure builds a table of each customer's TOTAL gross sales (`[Gross Sales]` evaluated per `'Customer'[Customer ID]`, so context transition gives the per-customer total). `_avgGross` is the average of those per-customer totals (the average gross sales per customer). It then counts how many customers have an individual total strictly greater than that average. Materializing the per-customer totals once in `_customers` means `[Gross Sales]` is computed a single time per customer and reused for both the average and the comparison, rather than re-evaluated.

## Assumptions
- "Average gross sales per customer" is interpreted as the mean of each customer's total gross sales (sum per customer, then averaged across customers) — not gross sales divided by customer count, which yields the same value but is stated here for clarity.
- The population of customers is `VALUES('Customer'[Customer ID])` in the current filter context. Customers with blank `[Gross Sales]` (no sales in context) are excluded from the average and the count, since `AVERAGEX`/the comparison ignore blanks; this counts only customers who actually have sales in the current context.
- "Exceed" is treated as strictly greater than (`>`). Change to `>=` if ties should be included.
- Uses the existing `[Gross Sales]` measure and the active relationship from `'Customer'` to `'Sales'`.
