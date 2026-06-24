# Measure templates (adapt, don't copy blindly)

> Patterns distilled in original wording from *The Definitive Guide to DAX*, SQLBI articles, and
> daxpatterns.com. Replace `'Date'`, `Sales`, `[Total Sales]`, etc. with the **real** names from the
> model context. Every template assumes a base measure and, for time intelligence, a **marked Date
> table** with one contiguous row per day. Prefer building on existing base measures over re-aggregating.

## Table of contents
1. Base aggregations
2. Ratios & percentages
3. % of total / share
4. Time intelligence — prior periods & growth
5. Time intelligence — to-date & rolling
6. Running / cumulative totals
7. Ranking & top-N
8. Distinct counts & "how many have X"
9. Semi-additive (balances, inventory)
10. "Within current selection" totals

---

## 1. Base aggregations
```dax
Total Sales   = SUMX ( Sales, Sales[Quantity] * Sales[Net Price] )   -- when no precomputed amount
Total Sales   = SUM ( Sales[Amount] )                                 -- when an amount column exists
Order Count   = DISTINCTCOUNT ( Sales[OrderNumber] )
```
Define base measures once and reuse them; downstream measures should reference `[Total Sales]`, not
re-derive the sum.

## 2. Ratios & percentages — always DIVIDE
```dax
Margin %      = DIVIDE ( [Total Margin], [Total Sales] )
Avg Price     = DIVIDE ( [Total Sales], [Total Quantity] )
```
`DIVIDE` returns blank on zero/blank denominator (pass a third argument for a custom fallback).

## 3. % of total / share
Clear the grouping you want the denominator to ignore with `REMOVEFILTERS`:
```dax
% of All Products =
DIVIDE ( [Total Sales], CALCULATE ( [Total Sales], REMOVEFILTERS ( 'Product' ) ) )

% of Category =                                  -- share within the product's own category
DIVIDE ( [Total Sales], CALCULATE ( [Total Sales], REMOVEFILTERS ( 'Product'[Subcategory], 'Product'[Product] ) ) )
```

## 4. Time intelligence — prior periods & growth
```dax
Sales PY =
CALCULATE ( [Total Sales], SAMEPERIODLASTYEAR ( 'Date'[Date] ) )

Sales YoY     = [Total Sales] - [Sales PY]
Sales YoY %   = DIVIDE ( [Total Sales] - [Sales PY], [Sales PY] )

Sales PM =                                        -- previous month
CALCULATE ( [Total Sales], DATEADD ( 'Date'[Date], -1, MONTH ) )
```
Pattern: capture the current value, shift the Date filter for the prior value, then compare. Using
`VAR` to freeze the current value first makes intent explicit:
```dax
Sales YoY % =
VAR _curr  = [Total Sales]
VAR _prior = CALCULATE ( [Total Sales], SAMEPERIODLASTYEAR ( 'Date'[Date] ) )
RETURN DIVIDE ( _curr - _prior, _prior )
```

## 5. Time intelligence — to-date & rolling
```dax
Sales YTD = CALCULATE ( [Total Sales], DATESYTD ( 'Date'[Date] ) )
Sales QTD = CALCULATE ( [Total Sales], DATESQTD ( 'Date'[Date] ) )
Sales MTD = CALCULATE ( [Total Sales], DATESMTD ( 'Date'[Date] ) )

-- Fiscal YTD ending June: DATESYTD ( 'Date'[Date], "06-30" )

Sales Rolling 12M =
CALCULATE (
    [Total Sales],
    DATESINPERIOD ( 'Date'[Date], MAX ( 'Date'[Date] ), -12, MONTH )
)
```

## 6. Running / cumulative totals
Use `ALLSELECTED` so the denominator/accumulation respects slicers but ignores the current row's date:
```dax
Sales Running Total =
CALCULATE (
    [Total Sales],
    FILTER ( ALLSELECTED ( 'Date'[Date] ), 'Date'[Date] <= MAX ( 'Date'[Date] ) )
)
```

## 7. Ranking & top-N
```dax
Product Rank =
RANKX ( ALL ( 'Product'[Product] ), [Total Sales], , DESC, DENSE )

Is Top 10 Product =                               -- use as a measure-filter / flag
IF ( [Product Rank] <= 10, 1, 0 )
```
Choose the `ALL(...)` scope deliberately — it defines the population being ranked.

## 8. Distinct counts & "how many have X"
```dax
Customers           = DISTINCTCOUNT ( Sales[CustomerKey] )

Customers Who Bought =                              -- distinct customers with sales > 0 this context
CALCULATE ( DISTINCTCOUNT ( Sales[CustomerKey] ), Sales[Quantity] > 0 )

New Customers =                                     -- first purchase falls in current period
VAR _firstPurchase =
    CALCULATETABLE (
        ADDCOLUMNS ( VALUES ( Sales[CustomerKey] ), "@first", CALCULATE ( MIN ( Sales[OrderDate] ) ) ),
        ALLEXCEPT ( Sales, Sales[CustomerKey] )
    )
RETURN
    COUNTROWS ( FILTER ( _firstPurchase, [@first] IN VALUES ( 'Date'[Date] ) ) )
```

## 9. Semi-additive (balances, inventory, headcount)
Values that sum across everything except time; take the last (or first) available date:
```dax
Closing Balance =
CALCULATE ( SUM ( Snapshot[Balance] ), LASTNONBLANK ( 'Date'[Date], CALCULATE ( COUNTROWS ( Snapshot ) ) ) )

Opening Balance =
CALCULATE ( SUM ( Snapshot[Balance] ), FIRSTNONBLANK ( 'Date'[Date], CALCULATE ( COUNTROWS ( Snapshot ) ) ) )
```

## 10. "Within current selection" totals
```dax
Sales % of Visible =
DIVIDE ( [Total Sales], CALCULATE ( [Total Sales], ALLSELECTED ( ) ) )
```
`ALLSELECTED()` with no argument means "everything the user selected, ignoring this visual's own
row/column grouping" — the correct denominator for share-of-visible-total in a matrix.

---

### How to use these
1. Pick the closest pattern to the business request.
2. Substitute real table/column/measure names from the model context.
3. Confirm the assumptions hold (marked Date table for §4–6; a unique key for distinct counts; a
   snapshot table for §9).
4. State any assumption back to the user when you deliver the measure.
