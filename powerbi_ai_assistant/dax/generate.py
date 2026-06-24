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


@dataclass
class ParsedMeasure:
    name: str          # suggested measure name, or "" if none could be extracted
    code: str          # the DAX code block, verbatim (may include the "Name =" prefix)
    raw: str           # the full LLM response (kept for the explanation panel)


def parse_measure_response(text: str) -> ParsedMeasure:
    """Extract the DAX code block and a suggested measure name from an LLM markdown response."""
    block = _DAX_FENCE.search(text) or _ANY_FENCE.search(text)
    code = block.group(1).strip() if block else text.strip()

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


def measure_expression(code: str, name: str) -> str:
    """Return just the measure body (RHS), stripping a leading `Name = ` assignment if present.

    Live evaluation needs the expression alone (it supplies its own probe measure name), so a generated
    `Total = SUM ( … )` must become `SUM ( … )`.
    """
    if name:
        assign = _NAME_ASSIGN.match(code)
        if assign:
            return code[assign.end():].strip()
    return code.strip()
