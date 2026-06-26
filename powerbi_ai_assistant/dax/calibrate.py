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
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..context.base import ModelContext
from ..core.artifact import ValidationResult
from .generate import has_dax_block, measure_expression, parse_measure_response
from .live_eval import SliceFilter
from .prompts import (
    DAX_SYSTEM_PROMPT,
    build_calibrate_diagnose_prompt,
    build_calibrate_interpret_prompt,
    build_calibrate_refine_prompt,
    build_calibrated_generate_prompt,
)

_GEN_MAX_TOKENS = 4000
_MAX_AUTO = 3  # auto-correction rounds before the controller forces a question to the user
_REL_TOL = 1e-4   # default: a relative miss under 0.01% counts as a match
_ABS_TOL = 0.01   # ...or an absolute miss under 1 cent


class SliceEvaluator(Protocol):
    def evaluate_at_slice(self, expression: str, home_table: str, filters: list[SliceFilter]) -> ValidationResult: ...


class _Provider(Protocol):
    def complete(self, system: str, messages: list[Any], **opts: Any) -> str: ...


@dataclass
class CalibrationPoint:
    """One calibration oracle: a known-correct value at a specific slice. The measure must reproduce
    `expected` (within tolerance) when evaluated under `filters`."""
    filters: list[SliceFilter]        # (table, column, value) — the slice this oracle value belongs to
    expected: float                   # the user's known-correct value at that slice


@dataclass
class CalibrationSession:
    request: str
    home_table: str
    points: list[CalibrationPoint] = field(default_factory=list)   # the calibration set — measure must hit ALL
    # Legacy single-point inputs (the current UI still passes these); folded into `points` in __post_init__.
    filters: list[SliceFilter] | None = None
    expected: float | None = None
    candidate: str = ""               # current DAX code (may include a "Name =" prefix)
    candidate_name: str = ""
    auto_attempts: int = 0
    status: str = "new"               # new | running | asking | passed | failed
    pending_question: str = ""
    last_actual: str = ""             # last test result(s), as text (for the diagnose prompt)
    rel_tol: float = _REL_TOL         # match tolerance (user-selectable in the UI)
    abs_tol: float = _ABS_TOL
    deep_think: bool = False          # enable the LLM's thinking mode for generate/diagnose/refine
    transcript: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Back-compat: build the single point from legacy filters/expected when no points were given.
        if not self.points and self.filters is not None and self.expected is not None:
            self.points = [CalibrationPoint(filters=list(self.filters), expected=float(self.expected))]
        # Keep the legacy single-point fields reflecting point #1 so the current (single-point) UI display
        # keeps working until the multi-point UI lands.
        if self.points:
            self.filters = self.points[0].filters
            self.expected = self.points[0].expected


# --------------------------------------------------------------------------- helpers

def _disp(value: Any) -> str:
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str):
        return f"'{value}'"
    return str(value)


def slice_desc(filters: list[SliceFilter]) -> str:
    return ", ".join(f"'{t}'[{c}] = {_disp(v)}" for t, c, v in filters) or "（整个模型，无切片）"


def point_desc(p: "CalibrationPoint") -> str:
    return f"{slice_desc(p.filters)} → {_num_str(p.expected)}"


def points_brief(points: list["CalibrationPoint"]) -> str:
    """Render the whole calibration set for a prompt: every slice and its required value."""
    return "\n".join(f"- 切片{i + 1}: {point_desc(p)}" for i, p in enumerate(points)) or "（无）"


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


def _results_text(session: CalibrationSession) -> str:
    """Render the latest per-point actual-vs-expected (with ✓/✗) for the diagnose prompt."""
    res = next((e for e in reversed(session.transcript) if e.get("kind") == "result"), None)
    if not res or not res.get("points"):
        return session.last_actual or "（未知）"
    return "\n".join(
        f"- 切片{i + 1} [{p['slice']}]: 实跑={p['actual_text']} / 期望={_num_str(p['expected'])} "
        f"{'✓ 命中' if p['ok'] else '✗ 未命中'}"
        for i, p in enumerate(res["points"])
    )


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
        schema, session.request, points_brief(session.points),
        _results_text(session), session.candidate, _transcript_text(session),
    )
    response = provider.complete(system=DAX_SYSTEM_PROMPT, messages=[user(prompt)],
                                 max_tokens=_GEN_MAX_TOKENS, enable_thinking=session.deep_think)
    _consume(session, response)


def _parse_json_obj(text: str) -> dict[str, Any] | None:
    """Pull a JSON object out of an LLM reply — a fenced ```json block if present, else the outermost
    {...}. Returns None when nothing parses, so callers can fall back to the plain-clarify path."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    raw = m.group(1) if m else None
    if raw is None:
        start, end = text.find("{"), text.rfind("}")
        raw = text[start:end + 1] if 0 <= start < end else None
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def _interpret_reply(session: CalibrationSession, provider: _Provider, reply: str) -> dict[str, Any] | None:
    """Ask the LLM whether the reply corrects a target value (oracle) or just clarifies the rule, returning
    a small JSON the controller applies deterministically. Always non-thinking — it's a fast classification."""
    from ..llm import user

    prompt = build_calibrate_interpret_prompt(points_brief(session.points), session.candidate, reply)
    resp = provider.complete(system=DAX_SYSTEM_PROMPT, messages=[user(prompt)],
                             max_tokens=600, enable_thinking=False)
    return _parse_json_obj(resp)


def _apply_target_updates(session: CalibrationSession, updates: Any) -> list[tuple[int, Any, float]]:
    """Apply oracle corrections {point (1-based), expected} to session.points. Returns the changes
    actually made, as (point#, old, new), so the caller can echo them back for the user to verify."""
    changed: list[tuple[int, Any, float]] = []
    for u in updates or []:
        try:
            idx = int(u["point"]) - 1
            new = float(u["expected"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= idx < len(session.points):
            old = session.points[idx].expected
            if not _matches(old, new, session.rel_tol, session.abs_tol):  # skip no-op "corrections"
                session.points[idx].expected = new
                changed.append((idx + 1, old, new))
    if session.points:  # keep the legacy single-point field in sync with point #1
        session.expected = session.points[0].expected
    return changed


def _test(session: CalibrationSession, evaluator: SliceEvaluator) -> bool:
    """Evaluate the candidate at EVERY calibration point; pass only if ALL points match. Records each
    point's actual/expected so the diagnose prompt (and, later, the UI) can show exactly what missed."""
    expr = measure_expression(session.candidate, session.candidate_name)
    per_point: list[dict[str, Any]] = []
    lines: list[str] = []
    all_ok = True
    for i, p in enumerate(session.points):
        vr = evaluator.evaluate_at_slice(expr, session.home_table, p.filters)
        actual_num: float | None = None
        if vr.run_verified and vr.ok:
            if isinstance(vr.sample, (int, float)) and not isinstance(vr.sample, bool):
                actual_num = float(vr.sample)
            actual_txt = _num_str(vr.sample)
            ok = _matches(p.expected, vr.sample, session.rel_tol, session.abs_tol)
        else:
            actual_txt = "执行出错：" + ("; ".join(vr.errors) or "未知错误")
            ok = False
        all_ok = all_ok and ok
        per_point.append({
            "slice": slice_desc(p.filters), "expected": p.expected,
            "actual": actual_num, "actual_text": actual_txt, "ok": ok,
        })
        lines.append(f"切片{i + 1} [{slice_desc(p.filters)}]: 实跑={actual_txt} / 期望={_num_str(p.expected)} {'✓' if ok else '✗'}")

    # Keep the single-point text terse (old behaviour) so the current UI is unchanged; verbose for many.
    session.last_actual = per_point[0]["actual_text"] if len(per_point) == 1 else "\n".join(lines)
    session.transcript.append({
        "role": "system", "kind": "result", "text": session.last_actual, "ok": all_ok,
        "actual": per_point[0]["actual"] if per_point else None,  # back-compat for the single-point UI
        "points": per_point,
    })
    return all_ok


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
            schema, session.request, points_brief(session.points), session.candidate, refine_request,
        )
        response = provider.complete(system=DAX_SYSTEM_PROMPT, messages=[user(prompt)],
                                     max_tokens=_GEN_MAX_TOKENS, enable_thinking=session.deep_think)
        _consume(session, response)
    elif user_reply is not None:
        session.transcript.append({"role": "user", "kind": "answer", "text": user_reply})
        session.auto_attempts = 0
        # The reply may CORRECT a target value (a mistyped oracle) or merely CLARIFY the rule. Let the LLM
        # classify it, then apply any value corrections deterministically (don't let the model chase the old
        # wrong number). If targets changed, just re-test the current candidate — it may now pass outright.
        interp = _interpret_reply(session, provider, user_reply)
        changed = _apply_target_updates(session, interp.get("updates")) if interp else []
        if changed:
            msg = "；".join(f"切片{i} 期望 {_num_str(o)} → {_num_str(n)}" for i, o, n in changed)
            session.transcript.append({"role": "system", "kind": "note", "text": "已按你的更正调整校准目标：" + msg})
            if session.candidate:
                session.status = "running"   # re-test against the corrected targets before diagnosing
            else:
                _diagnose(session, provider, schema)
        else:
            _diagnose(session, provider, schema)
    elif not session.candidate:
        prompt = build_calibrated_generate_prompt(
            schema, session.request, points_brief(session.points)
        )
        response = provider.complete(system=DAX_SYSTEM_PROMPT, messages=[user(prompt)],
                                     max_tokens=_GEN_MAX_TOKENS, enable_thinking=session.deep_think)
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
