"""
Parsing the LLM's DAX response.

The generate/optimize prompts ask the model for a fenced ```dax code block plus prose. This module pulls
the measure code (and a suggested name) back out of that markdown so the rest of the pipeline gets a clean
artifact. Kept dependency-free and pure so it's trivially unit-testable against canned responses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A fenced code block; prefer one tagged ```dax but accept any fenced block as a fallback.
_DAX_FENCE = re.compile(r"```dax\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_ANY_FENCE = re.compile(r"```[\w]*\s*\n(.*?)```", re.DOTALL)
# A measure assignment LHS: `Measure Name = ...` (name has no brackets/parens), optionally `MEASURE`-style.
_NAME_ASSIGN = re.compile(r"^\s*([^=\[\]()\n]+?)\s*=", re.MULTILINE)
# Noise lines models sometimes put inside a code block: divider rules (==== / ---- / ****) and markdown
# headers (## ). These are not DAX and must be stripped before the expression is run.
_NOISE_LINE = re.compile(r"^\s*(?:[=\-*_#]{3,}.*|#{1,6}\s.*)$")


def _strip_noise(code: str) -> str:
    return "\n".join(ln for ln in code.splitlines() if not _NOISE_LINE.match(ln)).strip()


@dataclass
class ParsedMeasure:
    name: str          # suggested measure name, or "" if none could be extracted
    code: str          # the DAX code block, verbatim (may include the "Name =" prefix)
    raw: str           # the full LLM response (kept for the explanation panel)


def parse_measure_response(text: str) -> ParsedMeasure:
    """Extract the DAX code block and a suggested measure name from an LLM markdown response.

    In chat mode the reply mixes reasoning, dividers and the measure, so we prefer a fenced block that
    actually *looks* like DAX (has a column/measure ref and an `=`), and never fall back to the whole
    prose — otherwise non-DAX text (e.g. `===== 基础度量 =====`) leaks into the expression and the engine
    rejects it.
    """
    blocks = [b.strip() for b in _DAX_FENCE.findall(text)] or [b.strip() for b in _ANY_FENCE.findall(text)]
    code = ""
    for b in blocks:
        if "[" in b and "=" in b:  # a measure references a column/measure and assigns
            code = b
            break
    if not code and blocks:
        code = blocks[0]

    name = ""
    assign = _NAME_ASSIGN.search(code)
    if assign:
        candidate = assign.group(1).strip().strip("'\"")
        # guard against false positives like a stray "VAR x =" being read as a name
        if candidate and not candidate.upper().startswith(("VAR ", "RETURN")):
            name = candidate

    return ParsedMeasure(name=name, code=code, raw=text)


def has_dax_block(text: str) -> bool:
    """True if the text contains a fenced code block (i.e. the model returned a measure, not prose).

    Used by calibrated generation to tell a revised measure from a clarifying question."""
    return bool(_DAX_FENCE.search(text) or _ANY_FENCE.search(text))


def split_measures(code: str) -> list[tuple[str, str]]:
    """Split a (possibly multi-measure) DAX block into [(name, expression)].

    Each measure runs from its top-level `Name = ` line to the next one; `VAR`/`RETURN` lines belong to the
    current measure, not a new one. This is what lets the app handle a model that emits a small measure
    library (base + derived) — each measure can then be validated and written individually.
    """
    cleaned = _strip_noise(code)
    bounds = [
        m for m in _NAME_ASSIGN.finditer(cleaned)
        if not m.group(1).strip().upper().startswith(("VAR ", "RETURN"))
    ]
    measures: list[tuple[str, str]] = []
    for i, m in enumerate(bounds):
        name = m.group(1).strip().strip("'\"")
        end = bounds[i + 1].start() if i + 1 < len(bounds) else len(cleaned)
        expr = cleaned[m.end():end].strip()
        if name and expr:
            measures.append((name, expr))
    return measures


def measure_expression(code: str, name: str) -> str:
    """Return just the measure body (RHS): everything after the first `Name = ` assignment.

    Strips divider/header noise first, then searches for the assignment anywhere (not only at the start),
    so leading prose or `==== 基础度量 ====` dividers the model emitted are dropped. Live evaluation needs
    the expression alone (it supplies its own probe name), so `Total = SUM ( … )` becomes `SUM ( … )`.
    """
    cleaned = _strip_noise(code)
    for m in _NAME_ASSIGN.finditer(cleaned):
        if not m.group(1).strip().upper().startswith(("VAR ", "RETURN")):
            return cleaned[m.end():].strip()
    return cleaned
