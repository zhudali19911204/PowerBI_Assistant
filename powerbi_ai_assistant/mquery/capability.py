"""
Data-cleaning capability — the phase-2 pillar (Power Query / M).

`CleanAction` turns a natural-language cleaning request into a grounded M query that builds on an existing
query, then runs the project's core loop: **generate -> static-check -> live refresh -> repair**. Static
checking catches structural and reference errors; live verification (when a Desktop engine is connected)
writes the query to a temporary table, refreshes it, and reads back the output schema — proving the M
actually runs against the real data source, or feeding the engine's error back to the LLM for a bounded
number of repairs. Without a live engine it degrades to static-only and says so honestly
(`run_verified=False`).

The interactive chat (`app/components._render_mquery_chat`) drives the same pieces directly for a
multi-turn UX; `CleanAction.run` is the single-shot, capability-level entry that mirrors the DAX
`GenerateAction`. The live M evaluator (an object with `evaluate_m(expression) -> ValidationResult`) is
passed via `req.extra["m_evaluator"]` when a Desktop connection is available.
"""

from __future__ import annotations

from ..context.base import ModelContext
from ..core.artifact import ValidationResult
from ..core.capability import Action, ActionRequest, ActionResult, Capability
from .artifact import MScriptArtifact
from .generate import parse_m_response
from .prompts import M_SYSTEM_PROMPT, build_clean_prompt, build_repair_prompt

# Generation can run long (a full let..in plus reasoning + explanation); give it room.
_GENERATE_MAX_TOKENS = 4000
_MAX_REPAIRS = 2  # how many times to feed a validation error back to the LLM before giving up


def _source_query(req: ActionRequest, ctx: ModelContext) -> str | None:
    """The query being cleaned: an explicit `req.extra['query']`, else the first table query in the model."""
    name = req.extra.get("query")
    if isinstance(name, str) and ctx.has_query(name):
        return name
    return next(iter(ctx.table_queries), None)


def _validate_once(req: ActionRequest, artifact: MScriptArtifact) -> ValidationResult:
    """Static check; if it passes and a live M evaluator is available, run-verify via a refresh round-trip."""
    static = artifact.validate(req.context)
    evaluator = req.extra.get("m_evaluator")
    if not static.ok or evaluator is None:
        return static  # static-only (broken statically, or no live engine connected)
    return evaluator.evaluate_m(artifact.content)


class CleanAction(Action):
    id = "clean"
    label = "清洗"

    def run(self, req: ActionRequest) -> ActionResult:
        if req.provider is None:
            raise ValueError("CleanAction 需要一个 LLMProvider（请先在设置中配置模型与 API Key）")
        if not req.text.strip():
            raise ValueError("请描述要做的清洗/转换")

        from ..llm import user  # local import keeps core/mquery decoupled from llm at module load

        query_name = _source_query(req, req.context)
        if query_name is None:
            raise ValueError("当前模型没有可清洗的 Power Query 查询（仅计算表无 M 可改写）")
        grounding = req.context.serialize_query_for_prompt(query_name)

        response = req.provider.complete(
            system=M_SYSTEM_PROMPT,
            messages=[user(build_clean_prompt(grounding, req.text, query_name))],
            max_tokens=_GENERATE_MAX_TOKENS,
        )
        parsed = parse_m_response(response)
        artifact = MScriptArtifact(parsed.code, name=query_name)
        explanation = parsed.raw

        # generate -> static -> live -> repair
        repairs: list[dict[str, object]] = []
        validation = _validate_once(req, artifact)
        while not validation.ok and len(repairs) < _MAX_REPAIRS:
            repairs.append({"attempt": len(repairs) + 1, "errors": list(validation.errors)})
            repair_response = req.provider.complete(
                system=M_SYSTEM_PROMPT,
                messages=[
                    user(build_repair_prompt(grounding, artifact.content, "; ".join(validation.errors), req.text))
                ],
                max_tokens=_GENERATE_MAX_TOKENS,
            )
            parsed = parse_m_response(repair_response)
            artifact = MScriptArtifact(parsed.code, name=query_name)
            explanation = parsed.raw
            validation = _validate_once(req, artifact)

        return ActionResult(
            artifacts=[artifact],
            explanation=explanation,
            meta={"query_name": query_name, "validation": validation, "repairs": repairs},
        )


class MQueryCapability(Capability):
    id = "mquery"
    name = "Power Query 助手"

    def actions(self) -> list[Action]:
        # explain lands here alongside clean as the UX matures
        return [CleanAction()]
