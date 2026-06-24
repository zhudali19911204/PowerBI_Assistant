"""M4 tests: DAX response parsing, static validation, and the generate action end to end (no network)."""

from __future__ import annotations

import pytest

from powerbi_ai_assistant.context import Column, Measure, ModelContext, Relationship
from powerbi_ai_assistant.core import ActionRequest
from powerbi_ai_assistant.dax import (
    DaxCapability,
    DaxMeasureArtifact,
    GenerateAction,
    parse_measure_response,
)
from powerbi_ai_assistant.llm.base import ChatMessage


def _model() -> ModelContext:
    return ModelContext(
        tables={
            "Sales": [Column("Amount", "decimal", "Sales"), Column("OrderDateKey", "int", "Sales")],
            "Date": [Column("Date", "date", "Date"), Column("Year", "int", "Date")],
        },
        relationships=[Relationship("Sales", "OrderDateKey", "Date", "DateKey")],
        measures=[Measure("Total Sales", "Sales", "SUM ( Sales[Amount] )")],
        date_tables=["Date"],
        calculated_tables={"Dim_Calendar": "CALENDARAUTO()"},
    )


class FakeProvider:
    """A canned LLMProvider — records the prompt it received and returns a fixed response."""

    model = "fake"

    def __init__(self, response: str) -> None:
        self.response = response
        self.seen_system = ""
        self.seen_messages: list[ChatMessage] = []

    def complete(self, system: str, messages: list[ChatMessage], **opts: object) -> str:
        self.seen_system = system
        self.seen_messages = messages
        return self.response

    def stream(self, system, messages, **opts):  # pragma: no cover - unused here
        yield self.response


# --------------------------------------------------------------------------- parsing

def test_parse_extracts_dax_block_and_name():
    text = (
        "Here is the measure:\n\n"
        "```dax\nTotal Amount = SUM ( Sales[Amount] )\n```\n\n"
        "It sums the sales amount."
    )
    parsed = parse_measure_response(text)
    assert parsed.name == "Total Amount"
    assert parsed.code == "Total Amount = SUM ( Sales[Amount] )"
    assert parsed.raw == text


def test_parse_falls_back_to_untagged_fence():
    parsed = parse_measure_response("```\nSUM ( Sales[Amount] )\n```")
    assert parsed.code == "SUM ( Sales[Amount] )"
    assert parsed.name == ""  # no `Name =` assignment


def test_parse_does_not_mistake_var_for_name():
    parsed = parse_measure_response("```dax\nVAR x = 1\nRETURN x\n```")
    assert parsed.name == ""


# --------------------------------------------------------------------------- static validation

def test_validate_passes_on_real_references():
    art = DaxMeasureArtifact("Total Amount = SUM ( Sales[Amount] )", name="Total Amount")
    vr = art.validate(_model())
    assert vr.ok and not vr.errors
    assert vr.run_verified is False  # static only, never claims execution


def test_validate_flags_ghost_column_as_error():
    art = DaxMeasureArtifact("X = SUM ( Sales[Ghost] )", name="X")
    vr = art.validate(_model())
    assert not vr.ok
    assert any("Ghost" in e for e in vr.errors)


def test_validate_flags_ghost_table_as_error():
    art = DaxMeasureArtifact("X = SUM ( Nope[Col] )", name="X")
    vr = art.validate(_model())
    assert not vr.ok
    assert any("Nope" in e for e in vr.errors)


def test_validate_unknown_measure_is_warning_not_error():
    art = DaxMeasureArtifact("X = [Total Sales] - [Not A Measure]", name="X")
    vr = art.validate(_model())
    assert vr.ok  # measures are warnings, not hard errors
    assert any("Not A Measure" in w for w in vr.warnings)


def test_validate_calculated_table_column_is_warning():
    art = DaxMeasureArtifact("X = MAX ( Dim_Calendar[Date] )", name="X")
    vr = art.validate(_model())
    assert vr.ok  # can't statically verify a calculated table's columns
    assert any("计算表" in w for w in vr.warnings)


def test_validate_unbalanced_parens():
    art = DaxMeasureArtifact("X = SUM ( Sales[Amount] ", name="X")
    vr = art.validate(_model())
    assert not vr.ok and any("括号" in e for e in vr.errors)


# --------------------------------------------------------------------------- generate action

def test_generate_action_end_to_end():
    provider = FakeProvider("```dax\nTotal Amount = SUM ( Sales[Amount] )\n```\nSums sales.")
    req = ActionRequest(text="按金额求和", context=_model(), provider=provider)
    result = GenerateAction().run(req)

    assert len(result.artifacts) == 1
    art = result.artifacts[0]
    assert isinstance(art, DaxMeasureArtifact)
    assert art.name == "Total Amount"
    assert result.meta["validation"].ok
    # the prompt actually carried the real schema (grounding)
    assert "Sales'[Amount]" in provider.seen_messages[0].content
    assert provider.seen_system.startswith("You are a senior")


def test_generate_action_requires_provider():
    req = ActionRequest(text="x", context=_model(), provider=None)
    with pytest.raises(ValueError, match="LLMProvider"):
        GenerateAction().run(req)


def test_generate_action_rejects_empty_text():
    req = ActionRequest(text="   ", context=_model(), provider=FakeProvider("x"))
    with pytest.raises(ValueError):
        GenerateAction().run(req)


def test_capability_exposes_generate():
    cap = DaxCapability()
    assert cap.id == "dax"
    actions = cap.actions()
    assert [a.id for a in actions] == ["generate"]
