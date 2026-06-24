"""M1 tests: the abstractions import, ModelContext serializes correctly, and the registry works."""

from __future__ import annotations

import pytest

from powerbi_ai_assistant.context import Column, Measure, ModelContext, Relationship
from powerbi_ai_assistant.core import Action, ActionRequest, ActionResult, Capability, registry


def _sample_model() -> ModelContext:
    return ModelContext(
        tables={
            "Sales": [
                Column("Amount", "decimal", "Sales"),
                Column("OrderDateKey", "int", "Sales"),
            ],
            "Date": [Column("Date", "date", "Date"), Column("Year", "int", "Date")],
            "Product": [Column("Category", "text", "Product", cardinality=12)],
        },
        relationships=[
            Relationship("Sales", "OrderDateKey", "Date", "DateKey"),
        ],
        measures=[Measure("Total Sales", "Sales", "SUM ( Sales[Amount] )")],
        date_tables=["Date"],
    )


def test_grounding_queries():
    m = _sample_model()
    assert m.has_table("Sales") and not m.has_table("Nope")
    assert m.has_column("Sales", "Amount") and not m.has_column("Sales", "Ghost")
    assert m.has_measure("Total Sales") and not m.has_measure("Missing")


def test_serialize_for_prompt_contains_real_objects():
    text = _sample_model().serialize_for_prompt()
    assert "'Sales'[Amount] (decimal)" in text
    assert "(marked Date table)" in text          # Date table flagged
    assert "~12 distinct" in text                  # cardinality hint rendered
    assert "[Total Sales] = SUM ( Sales[Amount] )" in text
    assert "->" in text                            # relationship rendered


def test_serialize_focus_trims_unrelated_tables():
    text = _sample_model().serialize_for_prompt(focus=["Sales"])
    assert "'Sales'" in text and "'Date'" in text  # Date kept (related to Sales)
    assert "'Product'" not in text                 # unrelated table dropped


def test_calculated_tables_recognized_and_serialized():
    m = ModelContext(
        tables={"Sales": [Column("Amount", "decimal", "Sales")]},
        calculated_tables={"Dim_Calendar": "CALENDARAUTO()"},
    )
    assert m.has_table("Dim_Calendar")          # recognized → not a false "non-existent" reject
    assert not m.has_table("Ghost")
    text = m.serialize_for_prompt()
    assert "CALCULATED TABLES" in text and "'Dim_Calendar'  (calculated)" in text


def test_registry_register_and_guard():
    registry.clear()

    class DummyCap(Capability):
        id = "dummy"
        name = "Dummy"

        def actions(self) -> list[Action]:
            return []

    cap = DummyCap()
    registry.register(cap)
    assert registry.get("dummy") is cap
    assert registry.all_capabilities() == [cap]

    with pytest.raises(ValueError):
        registry.register(cap)  # duplicate id rejected

    registry.clear()


def test_action_result_dataclasses_default_empty():
    req = ActionRequest(text="hi", context=ModelContext())
    res = ActionResult()
    assert req.extra == {} and res.artifacts == [] and res.meta == {}
