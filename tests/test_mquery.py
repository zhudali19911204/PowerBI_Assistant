"""Phase-2 tests: M parsing, static lint, and the generate -> static -> live -> repair loop (no engine)."""

from __future__ import annotations

from powerbi_ai_assistant.context import Column, ModelContext
from powerbi_ai_assistant.core import ActionRequest, ValidationResult
from powerbi_ai_assistant.mquery import (
    CleanAction,
    MScriptArtifact,
    has_m_block,
    parse_m_blocks,
    parse_m_response,
)
from powerbi_ai_assistant.llm.base import ChatMessage


def _model() -> ModelContext:
    return ModelContext(
        tables={"Sales": [Column("Amount", "double", "Sales"), Column("Region", "string", "Sales")]},
        table_queries={"Sales": 'let\n    Source = Csv.Document(file)\nin\n    Source'},
        shared_expressions={"P_Region": '"East" meta [IsParameterQuery=true]'},
    )


# ----------------------------------------------------------------------- parsing

def test_parse_m_response_prefers_powerquery_block():
    text = "推理...\n```powerquery\nlet\n    A = 1\nin\n    A\n```\n说明一句"
    parsed = parse_m_response(text)
    assert parsed.code == "let\n    A = 1\nin\n    A"


def test_parse_m_response_picks_let_block_over_prose_block():
    text = "```text\njust notes\n```\n```\nlet\n    A = 1\nin\n    A\n```"
    parsed = parse_m_response(text)
    assert "let" in parsed.code and "A = 1" in parsed.code


def test_parse_m_blocks_and_has_m_block():
    text = "```m\nlet A = 1 in A\n```"
    assert has_m_block(text)
    assert parse_m_blocks(text) == ["let A = 1 in A"]
    assert not has_m_block("no code here")


# ----------------------------------------------------------------------- static lint

def test_static_ok_for_grounded_query():
    m = (
        'let\n'
        '    Source = #"Sales",\n'
        '    #"Filtered Rows" = Table.SelectRows(Source, each [Region] <> null and [Region] <> ""),\n'
        '    #"Changed Type" = Table.TransformColumnTypes(#"Filtered Rows", {{"Amount", type number}})\n'
        'in\n'
        '    #"Changed Type"'
    )
    vr = MScriptArtifact(m, name="Sales").validate(_model())
    assert vr.ok and not vr.run_verified and vr.errors == []


def test_static_flags_unbalanced_brackets():
    m = 'let\n    A = Table.SelectRows(Source, each [X] = 1\nin\n    A'
    vr = MScriptArtifact(m).validate(_model())
    assert not vr.ok
    assert any("括号" in e for e in vr.errors)


def test_static_flags_let_without_in():
    m = 'let\n    A = 1'
    vr = MScriptArtifact(m).validate(_model())
    assert not vr.ok
    assert any("in" in e for e in vr.errors)


def test_static_warns_on_unknown_reference():
    m = 'let\n    A = #"Nonexistent Query",\n    B = A\nin\n    B'
    vr = MScriptArtifact(m).validate(_model())
    assert vr.ok  # unknown ref is a warning, not a hard error (live refresh is the real proof)
    assert any("Nonexistent Query" in w for w in vr.warnings)


def test_static_accepts_known_shared_expression_reference():
    m = 'let\n    A = #"P_Region",\n    B = #"Sales"\nin\n    B'
    vr = MScriptArtifact(m).validate(_model())
    assert vr.ok and vr.warnings == []  # both #"P_Region" and #"Sales" are real queries


def test_strings_and_comments_do_not_break_balance():
    m = (
        'let\n'
        '    // a comment with an unbalanced ( paren\n'
        '    A = Text.From("a )) string with ] brackets"),\n'
        '    B = #"Sales"\n'
        'in\n'
        '    B'
    )
    vr = MScriptArtifact(m).validate(_model())
    assert vr.ok and vr.errors == []


# ----------------------------------------------------------------------- generate -> static -> repair loop

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


class SeqMEvaluator:
    """Returns a scripted sequence of ValidationResults, one per evaluate_m call."""

    def __init__(self, results: list[ValidationResult]) -> None:
        self.results = results
        self.calls = 0
        self.seen: list[str] = []

    def evaluate_m(self, expression: str) -> ValidationResult:
        self.seen.append(expression)
        r = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        return r


_GOOD_M = '```powerquery\nlet\n    A = #"Sales"\nin\n    A\n```'


def test_live_verify_passes_first_try():
    provider = SeqProvider([_GOOD_M])
    evaluator = SeqMEvaluator([ValidationResult(ok=True, sample="3 行 × 2 列", run_verified=True)])
    req = ActionRequest(text="去空行", context=_model(), provider=provider,
                        extra={"query": "Sales", "m_evaluator": evaluator})
    res = CleanAction().run(req)

    vr = res.meta["validation"]
    assert vr.ok and vr.run_verified
    assert res.meta["repairs"] == []
    assert res.meta["query_name"] == "Sales"
    assert evaluator.seen and evaluator.seen[0].startswith("let")


def test_live_failure_triggers_repair_then_succeeds():
    provider = SeqProvider([
        '```powerquery\nlet\n    A = Table.TransformColumnTypes(#"Sales", {{"Bad", type number}})\nin\n    A\n```',
        _GOOD_M,
    ])
    evaluator = SeqMEvaluator([
        ValidationResult(ok=False, errors=['找不到列 "Bad"'], run_verified=True),
        ValidationResult(ok=True, sample="3 行 × 2 列", run_verified=True),
    ])
    req = ActionRequest(text="改类型", context=_model(), provider=provider,
                        extra={"query": "Sales", "m_evaluator": evaluator})
    res = CleanAction().run(req)

    assert res.meta["validation"].ok and res.meta["validation"].run_verified
    assert len(res.meta["repairs"]) == 1
    assert res.meta["repairs"][0]["errors"] == ['找不到列 "Bad"']
    assert provider.calls == 2  # one generate + one repair


def test_static_failure_repairs_without_evaluator():
    provider = SeqProvider([
        '```powerquery\nlet\n    A = Table.SelectRows(#"Sales", each [Region] = "East"\nin\n    A\n```',  # unbalanced
        _GOOD_M,
    ])
    req = ActionRequest(text="筛选", context=_model(), provider=provider, extra={"query": "Sales"})
    res = CleanAction().run(req)

    vr = res.meta["validation"]
    assert vr.ok and not vr.run_verified  # fixed, but static-only (no engine)
    assert len(res.meta["repairs"]) == 1


def test_repair_loop_is_bounded():
    bad = '```powerquery\nlet\n    A = Table.SelectRows(#"Sales", each [R] = 1\nin\n    A\n```'  # always unbalanced
    provider = SeqProvider([bad])
    req = ActionRequest(text="筛选", context=_model(), provider=provider, extra={"query": "Sales"})
    res = CleanAction().run(req)

    assert not res.meta["validation"].ok
    assert len(res.meta["repairs"]) == 2  # _MAX_REPAIRS, then gives up
    assert provider.calls == 3
