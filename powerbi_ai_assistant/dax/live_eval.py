"""
Live DAX evaluation — the run-verify half of the validation loop.

Static checks can only prove a measure *might* be right; only execution proves it. `LiveDesktopEvaluator`
defines the candidate measure on the open Desktop engine and runs it with `EVALUATE ROW(...)`, returning
either the real scalar value (success) or the engine's own error message (a *verified* failure). Either
way `run_verified=True`, so the product never presents unexecuted DAX as if it had run.

`evaluate_at_slice` runs the same measure under a specific filter context (a dimension slice) — the basis
of calibrated generation: compare the value at a slice the user knows the correct answer for.
"""

from __future__ import annotations

import datetime
from typing import Any

from ..context.live_source import _LiveSession, find_adomd_dll, find_instances
from ..core.artifact import ValidationResult

_PROBE = "__pbi_ai_probe"

# A single slice predicate: (table, column, value). Value is a real Python value from the engine.
SliceFilter = tuple[str, str, Any]


def _clean_error(exc: Exception) -> str:
    """The first, most meaningful line of an ADOMD/.NET exception message."""
    text = str(exc).strip()
    return text.splitlines()[0][:300] if text else type(exc).__name__


def _format_value(value: Any) -> str:
    """Render a Python value as a DAX literal for a filter predicate. Type-based so it matches the
    column: booleans → TRUE()/FALSE(), numbers → bare literal, everything else → a quoted string."""
    if isinstance(value, bool):
        return "TRUE()" if value else "FALSE()"
    if isinstance(value, (datetime.datetime, datetime.date)):
        return f"DATE({value.year},{value.month},{value.day})"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    return '"' + str(value).replace('"', '""') + '"'


class LiveDesktopEvaluator:
    """Evaluates a measure expression against an open Power BI Desktop engine on `port`."""

    def __init__(self, port: int, dll: str | None = None) -> None:
        self.port = port
        self.dll = dll or find_adomd_dll(find_instances())

    def evaluate_measure(self, expression: str, home_table: str) -> ValidationResult:
        """Run the measure in an empty filter context (whole model)."""
        return self._run(expression, home_table, f"[{_PROBE}]")

    def evaluate_at_slice(
        self, expression: str, home_table: str, filters: list[SliceFilter]
    ) -> ValidationResult:
        """Run the measure under a specific slice, e.g. CALCULATE([m], Dim[Col]=val, ...)."""
        if filters:
            preds = ", ".join(f"'{t}'[{c}] = {_format_value(v)}" for t, c, v in filters)
            value_expr = f"CALCULATE([{_PROBE}], {preds})"
        else:
            value_expr = f"[{_PROBE}]"
        return self._run(expression, home_table, value_expr)

    def _run(self, expression: str, home_table: str, value_expr: str) -> ValidationResult:
        if not self.dll:
            # No client DLL → we genuinely cannot run it; report honestly as not run-verified.
            return ValidationResult(
                ok=False, errors=["未找到 Power BI 的 ADOMD 客户端 DLL，无法实跑验证"], run_verified=False
            )
        dax = (
            f"DEFINE MEASURE '{home_table}'[{_PROBE}] = {expression}\n"
            f'EVALUATE ROW("value", {value_expr})'
        )
        try:
            with _LiveSession(self.port, self.dll) as session:
                rows = session.query(dax)
        except Exception as exc:  # noqa: BLE001 — the engine's rejection IS the result we want to capture
            return ValidationResult(ok=False, errors=[_clean_error(exc)], run_verified=True)

        value = next(iter(rows[0].values()), None) if rows else None
        return ValidationResult(ok=True, sample=value, run_verified=True)
