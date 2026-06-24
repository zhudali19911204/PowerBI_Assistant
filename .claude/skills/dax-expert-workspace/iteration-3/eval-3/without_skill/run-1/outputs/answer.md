# Retained Customers & Retention Rate

## Suggested names
- `Retained Customers`
- `Retention Rate`

## Measures

```dax
Retained Customers =
VAR CurrentMonthCustomers =
    DISTINCT ( Sales[Customer ID] )
VAR PriorMonthCustomers =
    CALCULATETABLE (
        DISTINCT ( Sales[Customer ID] ),
        DATEADD ( 'Date'[Date], -1, MONTH )
    )
VAR Retained =
    COUNTROWS (
        INTERSECT ( CurrentMonthCustomers, PriorMonthCustomers )
    )
RETURN
    Retained
```

```dax
Retention Rate =
VAR PriorMonthActive =
    CALCULATE (
        DISTINCTCOUNT ( Sales[Customer ID] ),
        DATEADD ( 'Date'[Date], -1, MONTH )
    )
RETURN
    DIVIDE ( [Retained Customers], PriorMonthActive )
```

## Explanation

**Context assumption.** Both measures are designed to be evaluated in a report
context that is filtered to a single month (e.g. a matrix sliced by
`'Date'[Year-Month]`, or by `'Date'[Year]` + `'Date'[Month Number]`). The
filter context on the marked `'Date'` table is what defines "the currently
selected month."

**Retained Customers.**
- `CurrentMonthCustomers` is the distinct set of `Sales[Customer ID]` values
  that appear in the current filter context (i.e. customers who purchased in
  the selected month).
- `PriorMonthCustomers` shifts the date filter back exactly one month using
  `DATEADD ( 'Date'[Date], -1, MONTH )`. Because `'Date'` is a marked, contiguous
  date table, `DATEADD` is the correct, reliable way to shift the period; it
  returns the distinct customers active in the immediately preceding month.
- `INTERSECT` keeps only the customer IDs present in *both* sets, and
  `COUNTROWS` counts them. That is exactly: customers who purchased in the
  selected month AND in the prior month.

`INTERSECT` is used (rather than a `FILTER` with `CONTAINS`) because it operates
on the distinct customer tables directly and is both concise and efficient.
Capturing `PriorMonthCustomers` in a `VAR` evaluates it once in the original
filter context, avoiding context-transition surprises.

**Retention Rate.**
- The denominator, `PriorMonthActive`, counts distinct customers active in the
  immediately preceding month — the same `DATEADD ( ..., -1, MONTH )` shift, so
  the numerator and denominator are aligned on the exact same "prior month."
- `DIVIDE` returns `BLANK()` instead of an error when the prior month has no
  active customers (e.g. the first month of data), so the measure degrades
  gracefully rather than throwing a divide-by-zero.

**Notes / caveats.**
- These measures rely on `DATEADD`, which requires a proper marked date table
  with contiguous days — which the model provides.
- If `Retention Rate` is placed in a context that spans more than one month
  (e.g. a yearly total row), `DATEADD` shifts the whole selected set back one
  month; the result is then the multi-month aggregate, not a simple monthly
  rate. For a clean per-month metric, display these at the month grain.
- Both measures count purchasing activity from the `Sales` fact via its active
  relationships to `'Date'` and `'Customer'`; no inactive relationships or
  `USERELATIONSHIP` are needed.
