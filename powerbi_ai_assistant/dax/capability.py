"""
DAX capability — the phase-1 MVP pillar.

`GenerateAction` turns a natural-language metric request into a grounded DAX measure and then runs the
project's core loop: **generate -> static-check -> live EVALUATE -> repair**. Static checking catches
non-existent references; live evaluation (when a Desktop engine is connected) proves the measure actually
runs and returns a value, or feeds the engine's error back to the LLM for a bounded number of repairs.
Without a live engine it degrades to static-only and says so honestly (`run_verified=False`).
"""

from __future__ import annotations

from ..context.base import ModelContext
from ..core.artifact import ValidationResult
from ..core.capability import Action, ActionRequest, ActionResult, Capability
from .artifact import DaxMeasureArtifact
from .generate import measure_expression, parse_measure_response
from .prompts import DAX_SYSTEM_PROMPT, build_generate_prompt, build_repair_prompt

# Generation can run long (VARs + explanation + assumptions); give it room.
_GENERATE_MAX_TOKENS = 4000
_MAX_REPAIRS = 2  # how many times to feed a validation error back to the LLM before giving up


def _home_table(ctx: ModelContext) -> str | None:
    """Any real table works as the DEFINE MEASURE home; the choice doesn't affect evaluation."""
    return next(iter(ctx.tables), None)


def _validate_once(req: ActionRequest, artifact: DaxMeasureArtifact, home: str | None) -> ValidationResult:
    """Static check; if it passes and a live evaluator is available, run-verify via EVALUATE."""
    static = artifact.validate(req.context)
    if not static.ok or req.evaluator is None or home is None:
        return static  # static-only (broken statically, or no live engine connected)
    expr = measure_expression(artifact.content, artifact.name)
    return req.evaluator.evaluate_measure(expr, home)


class GenerateAction(Action):
    id = "generate"
    label = "生成"

    def run(self, req: ActionRequest) -> ActionResult:
        if req.provider is None:
            raise ValueError("GenerateAction 需要一个 LLMProvider（请先在设置中配置模型与 API Key）")
        if not req.text.strip():
            raise ValueError("请描述要计算的业务指标")

        from ..llm import user  # local import keeps core/dax decoupled from llm at module load

        schema = req.context.serialize_for_prompt()
        response = req.provider.complete(
            system=DAX_SYSTEM_PROMPT,
            messages=[user(build_generate_prompt(model_schema=schema, request=req.text))],
            max_tokens=_GENERATE_MAX_TOKENS,
        )
        parsed = parse_measure_response(response)
        artifact = DaxMeasureArtifact(parsed.code, name=parsed.name)
        explanation = parsed.raw

        # generate -> static -> live -> repair
        home = _home_table(req.context)
        repairs: list[dict[str, object]] = []
        validation = _validate_once(req, artifact, home)
        while not validation.ok and len(repairs) < _MAX_REPAIRS:
            repairs.append({"attempt": len(repairs) + 1, "errors": list(validation.errors)})
            repair_response = req.provider.complete(
                system=DAX_SYSTEM_PROMPT,
                messages=[
                    user(build_repair_prompt(schema, artifact.content, "; ".join(validation.errors), req.text))
                ],
                max_tokens=_GENERATE_MAX_TOKENS,
            )
            parsed = parse_measure_response(repair_response)
            artifact = DaxMeasureArtifact(parsed.code, name=parsed.name)
            explanation = parsed.raw
            validation = _validate_once(req, artifact, home)

        return ActionResult(
            artifacts=[artifact],
            explanation=explanation,
            meta={"measure_name": artifact.name, "validation": validation, "repairs": repairs},
        )


class DaxCapability(Capability):
    id = "dax"
    name = "DAX 助手"

    def actions(self) -> list[Action]:
        # explain / optimize land here in M5
        return [GenerateAction()]
