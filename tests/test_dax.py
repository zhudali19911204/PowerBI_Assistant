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
    split_measures,
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


def test_split_measures_handles_dividers_and_vars():
    code = (
        "==================== 1. 基础 ====================\n"
        "销售额 = SUM ( Sales[Amount] )\n"
        "成本 = SUM ( Sales[Cost] )\n"
        "==================== 2. 派生 ====================\n"
        "毛利 =\nVAR s = [销售额]\nRETURN s - [成本]"
    )
    ms = split_measures(code)
    assert [n for n, _ in ms] == ["销售额", "成本", "毛利"]          # dividers dropped, 3 measures
    assert ms[0][1] == "SUM ( Sales[Amount] )"
    assert ms[2][1] == "VAR s = [销售额]\nRETURN s - [成本]"          # VAR/RETURN stay with their measure


def test_split_measures_single():
    assert split_measures("Total = SUM ( Sales[Amount] )") == [("Total", "SUM ( Sales[Amount] )")]


def test_split_measures_ignores_dax_comments_with_equals():
    # Regression: `//` / `--` / `/* */` comment lines that contain '=' must NOT be read as measure
    # boundaries (they used to shatter one measure into garbage with bare tokens leaking out).
    code = (
        "// 1. 基础聚合，已存在于模型中\n"
        "Income_PVM_Price = SUMX ( VALUES ( T[K] ), [Price] * [Qty] )  // 价格效应: (P1 - P0) * Q1\n"
        "Income_PVM_Mix =\n"
        "// Total Sales Change = Price + Volume + Mix\n"
        "/* Mix = Total Change - Price - Volume */\n"
        "VAR x = [Income_PVM_Price]\n"
        "RETURN x - [Base]"
    )
    ms = split_measures(code)
    assert [n for n, _ in ms] == ["Income_PVM_Price", "Income_PVM_Mix"]   # 2 measures, comments not boundaries
    assert "//" not in ms[0][1] and "Change" not in ms[1][1]              # no comment/bare token leakage
    assert ms[1][1] == "VAR x = [Income_PVM_Price]\nRETURN x - [Base]"


def test_parse_dax_blocks_one_object_per_block():
    from powerbi_ai_assistant.dax import parse_dax_blocks
    text = (
        "## 思考过程\n先基础再派生。\n\n"
        "```dax\nBase = SUM ( Sales[Amt] )\n```\n\n"
        "```dax\n选择 =\nVAR Sel = SELECTEDVALUE ( 'P'[Item] )\n"
        'RETURN SWITCH ( TRUE (), Sel = "A", [Base], Sel = "B", [Base] * 2, BLANK () )\n```\n\n说明。'
    )
    objs = parse_dax_blocks(text)
    assert [n for n, _ in objs] == ["Base", "选择"]          # one object per block, in order
    assert "SWITCH" in objs[1][1] and objs[1][1].count('Sel = "') == 2   # SWITCH measure kept whole


def test_parse_dax_blocks_preserves_comments_in_expression():
    from powerbi_ai_assistant.dax import parse_dax_blocks
    text = (
        "```dax\n// 价格效应\nIncome_Price =\n"
        "SUMX ( VALUES ( T[K] ), [Cur] - [Base] )  // (P1-P0)*Q1\n```"
    )
    objs = parse_dax_blocks(text)
    assert len(objs) == 1
    name, expr = objs[0]
    assert name == "Income_Price"           # leading comment stripped from the NAME
    assert "//" in expr                      # comments PRESERVED in the expression (written into the model)


def test_split_measures_keeps_switch_comparisons_inside_one_measure():
    # Regression: `x = "..."` comparison lines nested inside SWITCH(TRUE(), ...) are at paren depth >= 1
    # and must NOT be treated as measure boundaries (they used to shatter one SWITCH measure).
    code = (
        "选择 =\n"
        "VAR Sel = SELECTEDVALUE ( 'P'[Item] )\n"
        "RETURN\n"
        "SWITCH ( TRUE (),\n"
        '    Sel = "Price", [Income_Price],\n'
        '    Sel = "Vol", [Income_Vol],\n'
        "    BLANK ()\n"
        ")"
    )
    ms = split_measures(code)
    assert len(ms) == 1
    assert ms[0][0] == "选择"
    assert "SWITCH" in ms[0][1] and ms[0][1].count('Sel = "') == 2   # both comparisons stayed in the body


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
