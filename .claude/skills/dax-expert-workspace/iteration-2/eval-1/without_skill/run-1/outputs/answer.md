# Customers Above Avg

## Suggested name
`Customers Above Avg`

## Measure

```dax
Customers Above Avg =
VAR CustomerSales =
    ADDCOLUMNS (
        VALUES ( 'Customer'[Customer ID] ),
        "@Sales", [Gross Sales]
    )
VAR AvgPerCustomer =
    AVERAGEX ( CustomerSales, [@Sales] )
VAR Result =
    COUNTROWS (
        FILTER (
            CustomerSales,
            [@Sales] > AvgPerCustomer
        )
    )
RETURN
    Result
```

## Explanation

1. **Build a per-customer table.** `ADDCOLUMNS ( VALUES ( 'Customer'[Customer ID] ), "@Sales", [Gross Sales] )` produces one row per customer that is visible in the current filter context, with each customer's total gross sales. Because `[Gross Sales]` is evaluated inside the row context created by `ADDCOLUMNS`, context transition makes it compute the total for that single customer (respecting any other slicers/filters such as Year, Region, Category, etc.).

2. **Compute the average per customer.** `AVERAGEX ( CustomerSales, [@Sales] )` averages those per-customer totals. This is the "average gross sales per customer" benchmark, evaluated in the current filter context. Capturing it in the variable `AvgPerCustomer` ensures it is calculated once against the full visible customer set before the comparison.

3. **Count the customers above the average.** `FILTER ( CustomerSales, [@Sales] > AvgPerCustomer )` keeps only the customers whose total exceeds the benchmark, and `COUNTROWS` returns how many there are.

### Notes
- `VALUES ( 'Customer'[Customer ID] )` is used (rather than iterating the fact table) so the count is over distinct customers, and the customer dimension drives the grain cleanly via the active relationship.
- Using the captured table variable `CustomerSales` for both the average and the filter guarantees both steps use the exact same customer set and avoids recomputing `[Gross Sales]`.
- The comparison is strict (`>`), so customers exactly equal to the average are not counted; switch to `>=` if "at or above" is desired.
- All sales-based logic reuses the existing `[Gross Sales]` measure, so any future change to gross-sales definition flows through automatically.
```
