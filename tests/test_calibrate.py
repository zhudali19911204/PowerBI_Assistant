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


# --------------------------------------------------------------------- multi-point (phases ①+②)

from powerbi_ai_assistant.dax import CalibrationPoint  # noqa: E402


class KeyedSliceEvaluator:
    """Returns a value keyed by the slice's filter value(s) — so each point can resolve independently."""

    def __init__(self, by_value):
        self.by_value = by_value

    def evaluate_at_slice(self, expression, home_table, filters):
        return ValidationResult(ok=True, sample=self.by_value.get(tuple(v for _, _, v in filters)),
                                run_verified=True)


_PTS = [CalibrationPoint([("Dim", "Year", 2024)], 100.0),
        CalibrationPoint([("Dim", "Year", 2025)], 250.0)]


def _last_result(s):
    return [e for e in s.transcript if e["kind"] == "result"][-1]


def test_back_compat_single_point_folds_into_points():
    s = _session()
    assert len(s.points) == 1 and s.points[0].expected == 100.0
    assert s.filters == [("Dim", "Year", 2024)] and s.expected == 100.0   # legacy display fields kept


def test_multipoint_passes_only_when_all_match():
    s = CalibrationSession(request="r", home_table="Sales", points=list(_PTS))
    s = advance(s, provider=SeqProvider(["```dax\nM = SUM ( Sales[Amount] )\n```"]),
                evaluator=KeyedSliceEvaluator({(2024,): 100.0, (2025,): 250.0}), context=_model())
    assert s.status == "passed"
    pts = _last_result(s)["points"]
    assert len(pts) == 2 and all(p["ok"] for p in pts)


def test_multipoint_one_miss_blocks_pass():
    s = CalibrationSession(request="r", home_table="Sales", points=list(_PTS))
    s = advance(s, provider=SeqProvider(["```dax\nM = SUM ( Sales[Amount] )\n```"]),
                evaluator=KeyedSliceEvaluator({(2024,): 100.0, (2025,): 999.0}), context=_model())
    assert s.status != "passed"
    assert [p["ok"] for p in _last_result(s)["points"]] == [True, False]


def test_parse_json_obj_fenced_bare_and_none():
    from powerbi_ai_assistant.dax.calibrate import _parse_json_obj
    assert _parse_json_obj('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse_json_obj('blah {"a": 2, "b": 3} tail') == {"a": 2, "b": 3}
    assert _parse_json_obj("no json here") is None


def _asking_session(points):
    """A session paused on a question, with a candidate already proposed (the usual reply context)."""
    s = CalibrationSession(request="r", home_table="Sales", points=list(points))
    s.candidate, s.candidate_name, s.status = "M = SUM ( Sales[Amount] )", "M", "asking"
    return s


def test_reply_corrects_target_value_then_candidate_passes():
    # 2nd target was mistyped (38.0); the user corrects it to 34.28 in chat. The controller must update the
    # oracle deterministically and re-test the CURRENT candidate — which now hits both.
    pts = [CalibrationPoint([("Dim", "Year", 2024)], 100.0),
           CalibrationPoint([("Dim", "Year", 2025)], 38.0)]
    s = _asking_session(pts)
    provider = SeqProvider(['{"kind":"fix_targets","updates":[{"point":2,"expected":34.28}],"note":"更正切片2"}'])
    s = advance(s, provider=provider,
                evaluator=KeyedSliceEvaluator({(2024,): 100.0, (2025,): 34.28}),
                context=_model(), user_reply="第二个切片应该是 34.28")

    assert s.points[1].expected == 34.28          # oracle updated
    assert s.status == "passed"                   # current candidate now hits both
    assert provider.calls == 1                    # only the interpret call; re-test passed, no diagnose
    assert any(e["kind"] == "note" for e in s.transcript)   # the correction was echoed back


def test_reply_clarify_leaves_targets_unchanged():
    pts = [CalibrationPoint([("Dim", "Year", 2024)], 100.0)]
    s = _asking_session(pts)
    provider = SeqProvider([
        '{"kind":"clarify","updates":[],"note":"含税"}',          # interpret → not a value correction
        "```dax\nM = CALCULATE ( SUM ( Sales[Amount] ) )\n```",   # diagnose → corrected measure
    ])
    s = advance(s, provider=provider, evaluator=SeqSliceEvaluator([100.0]),
                context=_model(), user_reply="含税")

    assert s.points[0].expected == 100.0          # target untouched on a clarify
    assert provider.calls == 2                     # interpret + diagnose (the normal clarify path)


def test_diagnose_prompt_includes_all_points_and_per_point_results():
    from powerbi_ai_assistant.dax.calibrate import _results_text, points_brief
    from powerbi_ai_assistant.dax.prompts import build_calibrate_diagnose_prompt

    s = CalibrationSession(request="r", home_table="Sales", points=list(_PTS))
    # one failing test round so a per-point result exists
    s = advance(s, provider=SeqProvider(["```dax\nM = SUM ( Sales[Amount] )\n```"]),
                evaluator=KeyedSliceEvaluator({(2024,): 100.0, (2025,): 999.0}), context=_model())
    pts, results = points_brief(s.points), _results_text(s)
    assert "切片1" in pts and "切片2" in pts                 # both targets listed
    assert "✓ 命中" in results and "✗ 未命中" in results      # per-point pass/fail shown
    prompt = build_calibrate_diagnose_prompt("SCHEMA", s.request, pts, results, s.candidate, "(无)")
    assert "切片2" in prompt and "✗ 未命中" in prompt and "ALL targets" in prompt
