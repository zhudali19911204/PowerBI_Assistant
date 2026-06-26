# Cleaning Recipes

Ready-to-adapt step sequences for the common data-cleaning asks. Each assumes you are appending steps onto
an existing query's last step (shown as `#"Prev"`). Keep Power BI-style step names; set types last.

## Remove blank / empty rows

```m
#"Removed Blank Rows" = Table.SelectRows(#"Prev", each
    not List.IsEmpty(List.RemoveMatchingItems(Record.FieldValues(_), {"", null})))
```

For a single key column being blank:

```m
#"Removed Blank Keys" = Table.SelectRows(#"Prev", each [Customer Number] <> null and [Customer Number] <> "")
```

## Remove duplicate rows

```m
#"Removed Duplicates" = Table.Distinct(#"Prev")                       // fully identical rows
#"Removed Dup Keys"   = Table.Distinct(#"Prev", {"Customer Number"})  // unique per key (keeps first)
```

## Trim / clean text (all text columns)

```m
#"Trimmed Text" = Table.TransformColumns(#"Prev",
    List.Transform(Table.ColumnNames(#"Prev"), each {_, each if _ is text then Text.Trim(Text.Clean(_)) else _, type text}))
```

For a known set of columns, simpler:

```m
#"Trimmed" = Table.TransformColumns(#"Prev", {{"Name", Text.Trim, type text}, {"City", Text.Trim, type text}})
```

## Fix data types (with culture when locale-sensitive)

```m
#"Changed Type" = Table.TransformColumnTypes(#"Prev",
    {{"Order Date", type date}, {"Quantity", Int64.Type}, {"Price", type number}}, "en-US")
```

## Split a column

```m
#"Split by Dash" = Table.SplitColumn(#"Prev", "SKU",
    Splitter.SplitTextByDelimiter("-", QuoteStyle.None), {"SKU.Family", "SKU.Variant"})
```

## Merge columns into one

```m
#"Merged Key" = Table.AddColumn(#"Prev", "Cust&Mat Key",
    each Text.Combine({[Customer Number], [Material Number]}, "|"), type text)
```

## Replace values

```m
#"Replaced N/A" = Table.ReplaceValue(#"Prev", "N/A", null, Replacer.ReplaceValue, {"Region", "Segment"})
```

## Fill down a sparse column

```m
#"Filled Down" = Table.FillDown(#"Prev", {"Category"})
```

## Conditional / derived column

```m
#"Added Tier" = Table.AddColumn(#"Prev", "Tier",
    each if [Amount] >= 100000 then "A" else if [Amount] >= 10000 then "B" else "C", type text)
```

## Unpivot wide month columns to long

```m
#"Unpivoted" = Table.UnpivotOtherColumns(#"Prev", {"Customer", "Material"}, "Month", "Value")
```

## Group & aggregate

```m
#"Grouped" = Table.Group(#"Prev", {"Customer Number"},
    {{"Total Amount", each List.Sum([Amount]), type number}, {"Lines", each Table.RowCount(_), Int64.Type}})
```

## Append (stack) another query

```m
#"Appended Budget" = Table.Combine({#"Prev", #"Fact_Budget_Sales_DT"})
```

## Merge (join) another query and expand

```m
#"Merged Dim" = Table.NestedJoin(#"Prev", {"Material Number"}, #"Dim_Material&Customer", {"Material Number"}, "dim", JoinKind.LeftOuter),
#"Expanded Dim" = Table.ExpandTableColumn(#"Merged Dim", "dim", {"Division", "Product Group"}, {"Division", "Product Group"})
```

## Handle conversion errors instead of letting them ride

```m
#"Safe Qty" = Table.TransformColumns(#"Prev", {{"Quantity", each try Number.From(_) otherwise null, type number}}),
#"Dropped Bad Rows" = Table.RemoveRowsWithErrors(#"Safe Qty", {"Quantity"})
```

Order reminder: **promote headers → remove unneeded columns early → shape (split/merge/unpivot/filter) →
set types last → handle errors where conversions happen.**
