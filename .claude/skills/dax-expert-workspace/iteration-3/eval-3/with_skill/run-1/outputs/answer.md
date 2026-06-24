# Retained Customers & Retention Rate

## Business definition (restated)

- **Retained Customers** — count of distinct customers who purchased in the **currently selected month**
  *and* also purchased in the **immediately preceding month** (the set intersection of "active this month"
  and "active last month").
- **Retention Rate** — Retained Customers divided by the number of customers active in the **prior month**
  (the standard retention denominator: the at-risk base you could have retained).

## Measures

```dax
Retained Customers =
VAR _currentMonthCustomers =
    VALUES ( Sales[Customer ID] )                          -- distinct customers active in the selected month
VAR _priorMonthCustomers =
    CALCULATETABLE (
        VALUES ( Sales[Customer ID] ),
        PREVIOUSMONTH ( 'Date'[Date] )                      -- shift filter context one month back
    )
VAR _retained =
    INTERSECT ( _currentMonthCustomers, _priorMonthCustomers )  -- bought in BOTH months
RETURN
    COUNTROWS ( _retained )
```

```dax
Retention Rate =
VAR _priorMonthActive =
    CALCULATE (
        DISTINCTCOUNT ( Sales[Customer ID] ),
        PREVIOUSMONTH ( 'Date'[Date] )                      -- customers active in the prior month
    )
RETURN
    DIVIDE ( [Retained Customers], _priorMonthActive )
```

## Suggested names

- `Retained Customers`
- `Retention Rate`

## How they behave

`Retained Customers` builds the list of distinct `Sales[Customer ID]` visible in the current month, then
separately builds the list visible in the previous month using `PREVIOUSMONTH` to shift the `'Date'` filter
context back one month, and uses `INTERSECT` to keep only the customers that appear in **both** lists; the
result is the row count of that intersection. `Retention Rate` divides that retained count by the number of
distinct customers who were active in the prior month (the retention base), using `DIVIDE` so it returns
blank rather than erroring when no one was active last month.

Both measures are grain-agnostic: at a single month they return that month's value; `PREVIOUSMONTH` operates
on whatever month(s) the `'Date'` filter context contains, so they also aggregate correctly across higher
levels as long as the date selection resolves to a clean month context (see assumptions).

## Assumptions to confirm

- A **marked Date table** named `'Date'` with one contiguous row per day exists (stated in the model) — this
  is required for `PREVIOUSMONTH` to work reliably.
- The intended evaluation context is a **single month** (e.g. the visual is sliced/grouped by
  `'Date'[Year-Month]` or by `'Date'[Year]` + `'Date'[Month Number]`). `PREVIOUSMONTH` returns the full
  calendar month immediately before the selected month; if multiple non-contiguous months are selected the
  "preceding month" concept is ambiguous, as with any prior-period measure.
- "Made a purchase" means any row in `Sales` for that customer in the period. No filter on `Units > 0` or
  positive revenue is applied; if returns/zero-unit lines should be excluded, add e.g.
  `Sales[Units] > 0` as a filter inside the `CALCULATETABLE` / `CALCULATE` and to the current-month set.
- The active relationship `Sales[Order Date] -> 'Date'[Date]` is used to place each order line in a month.
```
