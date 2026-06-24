"""Tests for the calibrated-generation controller: pass-first-try, auto-repair, and the ask/answer loop."""

from __future__ import annotations

from powerbi_ai_assistant.context import Column, ModelContext
from powerbi_ai_assistant.core import ValidationResult
from powerbi_ai_assistant.dax import CalibrationSession, advance, slice_desc
from powerbi_ai_assistant.dax.calibrate import _matches


def _model() -> ModelContext:
    return ModelContext(tables={"Sales": [Column("Amount", "double", "Sales")]})


class SeqProvider:
    model = "fake"

    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    def complete(self, system, messages, **opts):
        i = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[i]


class SeqSliceEvaluator:
    def __init__(self, samples):
        self.samples = samples  # list of values (None=blank) returned per call
        self.calls = 0
        self.seen = []

    def evaluate_at_slice(self, expression, home_table, filters):
        self.seen.append((expression, tuple(filters)))
        v = self.samples[min(self.calls, len(self.samples) - 1)]
        self.calls += 1
        return ValidationResult(ok=True, sample=v, run_verified=True)


def _session():
    return CalibrationSession(
        request="某指标", filters=[("Dim", "Year", 2024)], expected=100.0, home_table="Sales"
    )


# --------------------------------------------------------------------- helpers

def test_matches_numeric_tolerance_and_blank():
    assert _matches(100.0, 100.0000001)
    assert not _matches(100.0, 99.0)
    assert not _matches(100.0, None)  # blank never matches a non-blank expected


def test_slice_desc_renders_predicates():
    assert slice_desc([("Dim", "Year", 2024)]) == "'Dim'[Year] = 2024"


# --------------------------------------------------------------------- controller paths

def test_pass_on_first_try():
    provider = SeqProvider(["```dax\nM = SUM ( Sales[Amount] )\n```"])
    evaluator = SeqSliceEvaluator([100.0])
    s = advance(_session(), provider=provider, evaluator=evaluator, context=_model())

    assert s.status == "passed"
    assert provider.calls == 1                      # one generate, no diagnose needed
    assert evaluator.seen[0][1] == (("Dim", "Year", 2024),)   # tested at the slice
    assert any(e["kind"] == "done" for e in s.transcript)


def test_auto_repair_then_pass():
    provider = SeqProvider([
        "```dax\nM = SUM ( Sales[Amount] )\n```",         # wrong
        "```dax\nM = CALCULATE ( SUM ( Sales[Amount] ) )\n```",  # corrected
    ])
    evaluator = SeqSliceEvaluator([50.0, 100.0])
    s = advance(_session(), provider=provider, evaluator=evaluator, context=_model())

    assert s.status == "passed"
    assert s.auto_attempts == 1
    assert provider.calls == 2 and evaluator.calls == 2


def test_asks_user_then_answer_resolves():
    provider = SeqProvider([
        "```dax\nM = SUM ( Sales[Amount] )\n```",   # initial, wrong
        "需要确认：这个值是否含税？",                  # ambiguous → a question (no dax)
        "```dax\nM = SUM ( Sales[Amount] ) * 1.1\n```",  # after the answer, corrected
    ])
    evaluator = SeqSliceEvaluator([50.0, 100.0])
    s = _session()

    s = advance(s, provider=provider, evaluator=evaluator, context=_model())
    assert s.status == "asking"
    assert "含税" in s.pending_question

    s = advance(s, provider=provider, evaluator=evaluator, context=_model(), user_reply="含税")
    assert s.status == "passed"
    assert any(e["kind"] == "answer" and e["text"] == "含税" for e in s.transcript)


def test_engine_error_is_a_failed_result():
    class ErrEval:
        def evaluate_at_slice(self, expression, home_table, filters):
            return ValidationResult(ok=False, errors=["列不存在"], run_verified=True)

    provider = SeqProvider(["```dax\nM = SUM ( Sales[Ghost] )\n```"])  # never fixed
    s = advance(_session(), provider=provider, evaluator=ErrEval(), context=_model())
    # exhausts auto budget, then asks the user
    assert s.status == "asking"
    assert any("执行出错" in e["text"] for e in s.transcript if e["kind"] == "result")
