"""M6 tests: measure-expression extraction and the generate -> static -> live -> repair loop (no engine)."""

from __future__ import annotations

from powerbi_ai_assistant.context import Column, Measure, ModelContext
from powerbi_ai_assistant.core import ActionRequest, ValidationResult
from powerbi_ai_assistant.dax import GenerateAction, measure_expression
from powerbi_ai_assistant.llm.base import ChatMessage


def _model() -> ModelContext:
    return ModelContext(
        tables={"Sales": [Column("Amount", "double", "Sales")]},
        measures=[Measure("Total Sales", "Sales", "SUM ( Sales[Amount] )")],
    )


class SeqProvider:
    """Returns a scripted sequence of responses (generate, then one per repair); repeats the last."""

    model = "fake"

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    def complete(self, system: str, messages: list[ChatMessage], **opts: object) -> str:
        i = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[i]

    def stream(self, system, messages, **opts):  # pragma: no cover
        yield ""


class SeqEvaluator:
    """Returns a scripted sequence of ValidationResults, one per evaluate_measure call."""

    def __init__(self, results: list[ValidationResult]) -> None:
        self.results = results
        self.calls = 0
        self.seen: list[str] = []

    def evaluate_measure(self, expression: str, home_table: str) -> ValidationResult:
        self.seen.append(expression)
        r = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        return r


# ----------------------------------------------------------------------- measure_expression

def test_measure_expression_strips_name():
    assert measure_expression("Total = SUM ( Sales[Amount] )", "Total") == "SUM ( Sales[Amount] )"


def test_measure_expression_without_name_returns_body():
    assert measure_expression("SUM ( Sales[Amount] )", "") == "SUM ( Sales[Amount] )"


# ----------------------------------------------------------------------- live verify, happy path

def test_live_verify_passes_first_try():
    provider = SeqProvider(["```dax\nM = SUM ( Sales[Amount] )\n```"])
    evaluator = SeqEvaluator([ValidationResult(ok=True, sample=42, run_verified=True)])
    req = ActionRequest(text="求和", context=_model(), provider=provider, evaluator=evaluator)
    res = GenerateAction().run(req)

    vr = res.meta["validation"]
    assert vr.ok and vr.run_verified and vr.sample == 42
    assert res.meta["repairs"] == []
    # the evaluator received the bare expression, not the "M =" assignment
    assert evaluator.seen == ["SUM ( Sales[Amount] )"]


# ----------------------------------------------------------------------- live failure -> repair fixes it

def test_live_failure_triggers_repair_then_succeeds():
    provider = SeqProvider([
        "```dax\nM = SUM ( Sales[Amount] ) + 1/0\n```",       # first attempt: runs but engine errors
        "```dax\nM = DIVIDE ( SUM ( Sales[Amount] ), 2 )\n```",  # repaired
    ])
    evaluator = SeqEvaluator([
        ValidationResult(ok=False, errors=["除以零"], run_verified=True),
        ValidationResult(ok=True, sample=7, run_verified=True),
    ])
    req = ActionRequest(text="求和", context=_model(), provider=provider, evaluator=evaluator)
    res = GenerateAction().run(req)

    assert res.meta["validation"].ok and res.meta["validation"].sample == 7
    assert len(res.meta["repairs"]) == 1
    assert res.meta["repairs"][0]["errors"] == ["除以零"]
    assert "DIVIDE" in res.artifacts[0].content        # final artifact is the repaired one
    assert provider.calls == 2                          # one generate + one repair


# ----------------------------------------------------------------------- static failure repairs w/o engine

def test_static_failure_repairs_without_evaluator():
    provider = SeqProvider([
        "```dax\nM = SUM ( Sales[Ghost] )\n```",   # references a non-existent column → static fails
        "```dax\nM = SUM ( Sales[Amount] )\n```",  # repaired to a real column
    ])
    req = ActionRequest(text="求和", context=_model(), provider=provider, evaluator=None)
    res = GenerateAction().run(req)

    vr = res.meta["validation"]
    assert vr.ok and not vr.run_verified            # fixed, but static-only (no engine)
    assert len(res.meta["repairs"]) == 1
    assert "Amount" in res.artifacts[0].content


# ----------------------------------------------------------------------- repairs are bounded

def test_repair_loop_is_bounded():
    provider = SeqProvider(["```dax\nM = SUM ( Sales[Ghost] )\n```"])  # never fixes it
    req = ActionRequest(text="求和", context=_model(), provider=provider, evaluator=None)
    res = GenerateAction().run(req)

    assert not res.meta["validation"].ok
    assert len(res.meta["repairs"]) == 2               # _MAX_REPAIRS, then gives up
    assert provider.calls == 3                          # 1 generate + 2 repairs
