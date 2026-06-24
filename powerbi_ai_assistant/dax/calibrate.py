"""
Calibrated DAX generation — example/oracle-driven, with a clarify loop.

The user supplies a known-correct value at one dimension slice; that value is the oracle. The controller
generates a measure, runs it **at that slice** (live), and compares to the oracle. On a mismatch it asks
the LLM to either auto-correct (up to a small budget) or — when the requirement is genuinely ambiguous —
pose one specific question to the user. Answering pins the requirement down; the loop repeats until the
measure reproduces the oracle. This catches measures that *run but are wrong*, which plain run-verification
cannot. State lives in `CalibrationSession` so it survives Streamlit reruns.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..context.base import ModelContext
from ..core.artifact import ValidationResult
from .generate import has_dax_block, measure_expression, parse_measure_response
from .live_eval import SliceFilter
from .prompts import (
    DAX_SYSTEM_PROMPT,
    build_calibrate_diagnose_prompt,
    build_calibrate_refine_prompt,
    build_calibrated_generate_prompt,
)

_GEN_MAX_TOKENS = 4000
_MAX_AUTO = 2  # auto-correction rounds before the controller forces a question to the user
_REL_TOL = 1e-4   # default: a relative miss under 0.01% counts as a match
_ABS_TOL = 0.01   # ...or an absolute miss under 1 cent


class SliceEvaluator(Protocol):
    def evaluate_at_slice(self, expression: str, home_table: str, filters: list[SliceFilter]) -> ValidationResult: ...


class _Provider(Protocol):
    def complete(self, system: str, messages: list[Any], **opts: Any) -> str: ...


@dataclass
class CalibrationSession:
    request: str
    filters: list[SliceFilter]        # (table, column, value) — the slice the oracle value belongs to
    expected: float                   # the user's known-correct value at that slice
    home_table: str
    candidate: str = ""               # current DAX code (may include a "Name =" prefix)
    candidate_name: str = ""
    auto_attempts: int = 0
    status: str = "new"               # new | running | asking | passed | failed
    pending_question: str = ""
    last_actual: str = ""             # last slice result, as text (for the diagnose prompt)
    rel_tol: float = _REL_TOL         # match tolerance (user-selectable in the UI)
    abs_tol: float = _ABS_TOL
    transcript: list[dict[str, Any]] = field(default_factory=list)


# --------------------------------------------------------------------------- helpers

def _disp(value: Any) -> str:
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str):
        return f"'{value}'"
    return str(value)


def slice_desc(filters: list[SliceFilter]) -> str:
    return ", ".join(f"'{t}'[{c}] = {_disp(v)}" for t, c, v in filters) or "（整个模型，无切片）"


def _num_str(value: Any) -> str:
    if value is None:
        return "（空白 BLANK）"
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return str(value)


def _matches(expected: float, actual: Any, rel_tol: float = _REL_TOL, abs_tol: float = _ABS_TOL) -> bool:
    if actual is None:
        return False
    try:
        return math.isclose(float(actual), float(expected), rel_tol=rel_tol, abs_tol=abs_tol)
    except (TypeError, ValueError):
        return str(actual) == str(expected)


def _transcript_text(session: CalibrationSession) -> str:
    lines: list[str] = []
    for e in session.transcript:
        kind = e.get("kind")
        if kind == "question":
            lines.append("AI 问: " + e["text"])
        elif kind == "answer":
            lines.append("用户答: " + e["text"])
        elif kind == "result":
            lines.append("实跑值: " + e["text"])
    return "\n".join(lines[-12:]) or "（无）"


def _consume(session: CalibrationSession, response: str) -> None:
    """Interpret an LLM reply: a dax block → a revised measure to test; otherwise → a question."""
    if has_dax_block(response):
        parsed = parse_measure_response(response)
        session.candidate = parsed.code
        session.candidate_name = parsed.name
        session.transcript.append({"role": "ai", "kind": "measure", "text": parsed.code, "name": parsed.name})
        session.status = "running"
    else:
        question = response.strip()
        session.pending_question = question
        session.transcript.append({"role": "ai", "kind": "question", "text": question})
        session.status = "asking"


def _diagnose(session: CalibrationSession, provider: _Provider, schema: str) -> None:
    from ..llm import user

    prompt = build_calibrate_diagnose_prompt(
        schema, session.request, slice_desc(session.filters),
        str(session.expected), session.last_actual or "（未知）", session.candidate, _transcript_text(session),
    )
    response = provider.complete(system=DAX_SYSTEM_PROMPT, messages=[user(prompt)], max_tokens=_GEN_MAX_TOKENS)
    _consume(session, response)


def _test(session: CalibrationSession, evaluator: SliceEvaluator) -> bool:
    expr = measure_expression(session.candidate, session.candidate_name)
    vr = evaluator.evaluate_at_slice(expr, session.home_table, session.filters)
    actual_num: float | None = None
    if vr.run_verified and vr.ok:
        if isinstance(vr.sample, (int, float)) and not isinstance(vr.sample, bool):
            actual_num = float(vr.sample)
        session.last_actual = _num_str(vr.sample)
        passed = _matches(session.expected, vr.sample, session.rel_tol, session.abs_tol)
    else:
        session.last_actual = "执行出错：" + ("; ".join(vr.errors) or "未知错误")
        passed = False
    session.transcript.append(
        {"role": "system", "kind": "result", "text": session.last_actual, "ok": passed, "actual": actual_num}
    )
    return passed


# --------------------------------------------------------------------------- controller

def advance(
    session: CalibrationSession,
    *,
    provider: _Provider,
    evaluator: SliceEvaluator,
    context: ModelContext,
    user_reply: str | None = None,
    refine_request: str | None = None,
) -> CalibrationSession:
    """Advance the calibration by one user-facing step: initial generate, a reply to a question, or a
    post-success refinement (which is re-tested so the measure stays correct)."""
    from ..llm import user

    schema = context.serialize_for_prompt()

    if refine_request is not None:
        session.transcript.append({"role": "user", "kind": "refine", "text": refine_request})
        session.auto_attempts = 0
        prompt = build_calibrate_refine_prompt(
            schema, session.request, slice_desc(session.filters), str(session.expected),
            session.candidate, refine_request,
        )
        response = provider.complete(system=DAX_SYSTEM_PROMPT, messages=[user(prompt)], max_tokens=_GEN_MAX_TOKENS)
        _consume(session, response)
    elif user_reply is not None:
        session.transcript.append({"role": "user", "kind": "answer", "text": user_reply})
        session.auto_attempts = 0
        _diagnose(session, provider, schema)
    elif not session.candidate:
        prompt = build_calibrated_generate_prompt(
            schema, session.request, slice_desc(session.filters), str(session.expected)
        )
        response = provider.complete(system=DAX_SYSTEM_PROMPT, messages=[user(prompt)], max_tokens=_GEN_MAX_TOKENS)
        _consume(session, response)

    if session.status == "asking":
        return session

    # test + bounded auto-repair
    while session.status == "running":
        if _test(session, evaluator):
            session.status = "passed"
            session.transcript.append({"role": "system", "kind": "done", "text": f"命中：{session.last_actual}"})
            return session
        if session.auto_attempts >= _MAX_AUTO:
            break
        session.auto_attempts += 1
        _diagnose(session, provider, schema)  # may revise (loop) or ask (exits loop)

    # auto budget spent and still failing → force a question to the user
    if session.status == "running":
        _diagnose(session, provider, schema)
        if session.status == "running":  # LLM kept revising; stop blind looping and ask
            session.status = "asking"
            session.pending_question = (
                "我多次自动调整仍未命中。请补充一个关键口径（例如：是否含税 / 同比口径 / 跨月还是单月 / 是否去重）。"
            )
            session.transcript.append({"role": "ai", "kind": "question", "text": session.pending_question})
    return session
