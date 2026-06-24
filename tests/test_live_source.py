"""Tests for the live source. The pure DMV->ModelContext builder is tested with synthetic rows (no
engine needed); discovery is smoke-tested; a real-connection test is gated behind an env flag."""

from __future__ import annotations

import os

import pytest

from powerbi_ai_assistant.context import find_instances
from powerbi_ai_assistant.context.live_source import build_model_context


def _rows():
    tables = [
        {"ID": 1, "Name": "Sales", "DataCategory": None},
        {"ID": 2, "Name": "Date", "DataCategory": "Time"},
        {"ID": 3, "Name": "Calc", "DataCategory": None},          # a calculated table (columns exposed live)
        {"ID": 9, "Name": "LocalDateTable_abc", "DataCategory": None},  # auto-date noise → dropped
    ]
    columns = [
        {"ID": 101, "TableID": 1, "ExplicitName": "Amount", "InferredName": None, "ExplicitDataType": 8, "Type": 1},
        {"ID": 102, "TableID": 1, "ExplicitName": None, "InferredName": "RowNumber-x", "ExplicitDataType": 6, "Type": 3},
        {"ID": 103, "TableID": 2, "ExplicitName": "Date", "InferredName": None, "ExplicitDataType": 9, "Type": 1},
        {"ID": 104, "TableID": 3, "ExplicitName": "CalcCol", "InferredName": None, "ExplicitDataType": 2, "Type": 4},
        {"ID": 105, "TableID": 9, "ExplicitName": "AutoCol", "InferredName": None, "ExplicitDataType": 9, "Type": 1},
    ]
    relationships = [
        {"FromTableID": 1, "FromColumnID": 101, "ToTableID": 2, "ToColumnID": 103, "IsActive": True, "CrossFilteringBehavior": 1},
        {"FromTableID": 1, "FromColumnID": 101, "ToTableID": 3, "ToColumnID": 104, "IsActive": False, "CrossFilteringBehavior": 2},
        {"FromTableID": 1, "FromColumnID": 101, "ToTableID": 9, "ToColumnID": 105, "IsActive": True, "CrossFilteringBehavior": 1},
    ]
    measures = [{"TableID": 1, "Name": "Total", "Expression": " SUM ( Sales[Amount] ) "}]
    return tables, columns, relationships, measures


def test_build_drops_auto_date_tables_and_rownumber_columns():
    ctx = build_model_context(*_rows())
    assert set(ctx.tables) == {"Sales", "Date", "Calc"}        # LocalDateTable_* gone
    assert [c.name for c in ctx.tables["Sales"]] == ["Amount"]  # RowNumber column dropped
    assert ctx.tables["Sales"][0].dtype == "double"            # ExplicitDataType 8 → double


def test_build_exposes_calculated_table_columns():
    # the whole reason for going live: calc tables show real columns and count as regular tables
    ctx = build_model_context(*_rows())
    assert ctx.has_table("Calc") and ctx.has_column("Calc", "CalcCol")
    assert ctx.calculated_tables == {}  # nothing special-cased; live exposes them as normal tables


def test_build_relationships_resolve_names_and_drop_auto_date():
    ctx = build_model_context(*_rows())
    pairs = {(r.from_table, r.from_column, r.to_table, r.to_column, r.cross_filter, r.is_active) for r in ctx.relationships}
    assert ("Sales", "Amount", "Date", "Date", "single", True) in pairs
    assert ("Sales", "Amount", "Calc", "CalcCol", "both", False) in pairs   # both-direction + inactive preserved
    assert len(ctx.relationships) == 2                                       # the LocalDateTable rel is dropped


def test_build_marks_date_table_and_measures():
    ctx = build_model_context(*_rows())
    assert ctx.date_tables == ["Date"]
    assert len(ctx.measures) == 1
    m = ctx.measures[0]
    assert m.name == "Total" and m.table == "Sales" and m.expression == "SUM ( Sales[Amount] )"


def test_find_instances_returns_list_without_crashing():
    # On a machine with no Desktop open this is just [], but it must never raise.
    assert isinstance(find_instances(), list)


@pytest.mark.skipif(not os.getenv("POWERBI_LIVE_TEST"), reason="set POWERBI_LIVE_TEST=1 with a report open in Desktop")
def test_live_connect_real_instance():
    from powerbi_ai_assistant.context import LiveDesktopSource

    instances = find_instances()
    assert instances, "no Power BI Desktop instance found"
    ctx = LiveDesktopSource(instances[0].port).load()
    assert ctx.tables and ctx.measures
