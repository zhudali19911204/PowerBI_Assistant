"""
Prompt assets for the DAX capability.

This module distills the project's `dax-expert` skill into runtime prompts. The skill (see
`.claude/skills/dax-expert/`) is the canonical, longer-form knowledge base used during development and
benchmarking; this file is the *compressed* version that ships inside the product and is sent to the
LLM at request time. Keep the two in sync: when a real failure teaches us something (the way the
nested-iterator trap below came out of an eval), update the skill first, then fold the lesson here.

Design notes:
- Pure strings + builders, no third-party dependencies, so this stays trivially importable and testable.
- The model schema is injected as text via `ModelContext.serialize_for_prompt()` (see
  `powerbi_ai_assistant/context/`). Grounding the prompt in the *real* schema is what stops the model
  from inventing columns, so the builders require it.
"""

from __future__ import annotations

# --------------------------------------------------------------------------------------------------
# System prompt — the persona and the non-negotiable rules. Phrased to explain *why*, because the
# model reasons better from rationale than from bare prohibitions.
# --------------------------------------------------------------------------------------------------

DAX_SYSTEM_PROMPT = """\
You are a senior Power BI / Tabular engineer writing DAX. DAX looks like a formula language but
behaves like a query engine: most wrong answers and most slow measures come from misunderstanding
evaluation context, not from syntax. Reason about context explicitly before reaching for functions.

GROUNDING (the rule that prevents the most damage)
- Reference ONLY tables, columns, and measures that appear in the provided model schema. A measure
  that cites a column which does not exist is worse than no measure: it looks right and fails at
  runtime. If the schema is missing something you need, say so instead of inventing it.
- Use fully-qualified column references `Table[Column]` and bare measure references `[Measure]`.
- Build on existing base measures rather than re-deriving aggregations.
- Prefer measures over calculated columns unless a physical column is truly required.

EVALUATION CONTEXT (reason about it first)
- Row context = "the current row" (calculated columns and iterators like SUMX/AVERAGEX/FILTER). It does
  NOT filter the model by itself.
- Filter context = "what is currently visible" (visual, slicers, CALCULATE). Aggregations read it.
- Context transition: CALCULATE — and every measure reference, which wraps an implicit CALCULATE —
  turns the current row context into a filter context. This is what makes a measure inside an iterator
  evaluate per-row.

THE NESTED-ITERATOR TRAP (state this to yourself on every nested iteration)
- When you iterate one table and aggregate a DIFFERENT table inside, the outer row context does NOT
  filter the inner table. Without a CALCULATE (or a measure reference) the inner aggregation silently
  recomputes over the whole filter context — code that READS as per-row but isn't.
  WRONG:  AVERAGEX ( VALUES ( 'Date'[Date] ), SUMX ( 'Inventory', 'Inventory'[On Hand] * ... ) )
  RIGHT:  AVERAGEX ( VALUES ( 'Date'[Date] ), CALCULATE ( SUMX ( 'Inventory', 'Inventory'[On Hand] * ... ) ) )
  The source table of an inner iterator is likewise unscoped unless transitioned. This bug compiles and
  looks self-consistent, so when execution is available, PROVE the measure by running it, don't trust
  the read-through.

CONVENTIONS (these are correctness and performance habits, not style)
- Use VAR generously: it improves readability, avoids recomputation, and freezes a value in the context
  where it is defined (e.g. capture the current value before CALCULATE shifts the context).
- Always DIVIDE(numerator, denominator) instead of `/` — it returns blank/your fallback on zero, and a
  separate IF(...>0) guard is then redundant.
- Filter with column predicates (`CALCULATE([m], T[col]="x")`), not whole-table FILTER, when possible.
- KEEPFILTERS to intersect, REMOVEFILTERS/ALL to clear — know which you mean (e.g. % of total clears a
  grouping; "within selection" keeps it; ALLSELECTED = "what the user selected, ignoring this visual").
- Time intelligence requires a marked Date table with contiguous dates; say so when you rely on it.
- Format the code: one clause per line, VAR/RETURN aligned.

VALIDATE before declaring done: every reference exists in the schema; parentheses/arities balanced;
division via DIVIDE; nested iterators carry CALCULATE/measure transition; returns a scalar of the
expected type (never text from FORMAT where a number is expected).
"""


# --------------------------------------------------------------------------------------------------
# Per-action user-prompt builders. Each injects the serialized model schema so the answer is grounded.
# `model_schema` is the output of ModelContext.serialize_for_prompt().
# --------------------------------------------------------------------------------------------------

_SCHEMA_BLOCK = "<MODEL SCHEMA>\n{model_schema}\n</MODEL SCHEMA>"


def build_generate_prompt(model_schema: str, request: str) -> str:
    """Natural-language business metric -> a grounded DAX measure."""
    return f"""\
Write a Power BI DAX measure for the request below, grounded in the model schema.

REQUEST:
{request}

{_SCHEMA_BLOCK.format(model_schema=model_schema)}

Respond with:
1. A `dax` code block containing the measure, with a suggested measure name.
2. A 1-3 sentence plain-language explanation of how it behaves.
3. Any assumption the user should confirm (e.g. "assumes a marked Date table named 'Date'").
Reference only objects that exist in the schema above."""


def build_explain_prompt(model_schema: str, measure: str) -> str:
    """Explain an existing measure in evaluation order."""
    return f"""\
Explain the following DAX measure, grounded in the model schema. Walk through it in evaluation order:
what each VAR captures and in what context, the filter context when each aggregation runs, where any
context transition occurs, and what the final RETURN produces. Explain the *why*, and flag any subtle
behavior (blanks, context transition, filter modifiers, the nested-iterator trap) the reader might miss.

MEASURE:
```dax
{measure}
```

{_SCHEMA_BLOCK.format(model_schema=model_schema)}"""


def build_optimize_prompt(model_schema: str, measure: str) -> str:
    """Optimize an existing measure for performance/safety/clarity."""
    return f"""\
Optimize the following DAX measure, grounded in the model schema. Scan for anti-patterns: whole-table
FILTER, `/` instead of DIVIDE, a redundant IF divide-by-zero guard, repeated subexpressions not stored
in VAR, unnecessary calculated columns, redundant CALCULATE, expensive context transition inside large
iterators, the nested-iterator trap (inner aggregation missing CALCULATE), and FORMAT producing text
used numerically.

MEASURE:
```dax
{measure}
```

{_SCHEMA_BLOCK.format(model_schema=model_schema)}

Respond with:
1. A `dax` code block with the rewritten measure.
2. A short bullet list of what changed and why each change is faster or safer — verified by reasoning,
   not asserted. Label each change as correctness/safety, readability, or real performance. If a change
   only improves readability and not speed, say so honestly rather than claiming a speedup."""


def build_repair_prompt(model_schema: str, failed_measure: str, error: str, request: str) -> str:
    """Repair a measure that failed validation (static reference error or a live EVALUATE engine error)."""
    return f"""\
The DAX measure below FAILED validation against the real model. Fix it so it executes correctly.

ORIGINAL REQUEST:
{request}

FAILED MEASURE:
```dax
{failed_measure}
```

VALIDATION ERROR (from static checks or the engine running EVALUATE):
{error}

{_SCHEMA_BLOCK.format(model_schema=model_schema)}

Diagnose the cause (most often a non-existent column/measure, a type mismatch, or a missing CALCULATE /
context transition), then return a corrected `dax` measure grounded only in the schema above, plus one
sentence on what you changed. Do not repeat the same mistake."""


def build_calibrated_generate_prompt(model_schema: str, request: str, slice_desc: str, expected: str) -> str:
    """First candidate for calibrated generation: the user has a known-correct value at one slice."""
    return f"""\
Write a Power BI DAX measure for the request, grounded in the schema. The user has hand-computed the
correct value at ONE specific slice — treat it as ground truth your measure must reproduce there.

REQUEST:
{request}

CALIBRATION (the measure MUST return this at the given slice):
- At slice: {slice_desc}
- Correct value: {expected}

{_SCHEMA_BLOCK.format(model_schema=model_schema)}

Reason about the evaluation context this slice implies (which filters are active), then return a `dax`
code block with the measure and a one-line note on how it behaves. Reference only objects in the schema."""


def build_calibrate_diagnose_prompt(
    model_schema: str, request: str, slice_desc: str, expected: str, actual: str, candidate: str, transcript: str
) -> str:
    """The measure ran but the slice value is wrong (or it errored). Either fix it, or ask the user.

    The reply is interpreted by the caller: a ```dax block = a revised measure to re-test; no dax block
    = a clarifying question shown to the user. This is the loop that forces a precise requirement.
    """
    return f"""\
You are calibrating a DAX measure against a value the user knows is correct, and it does not match yet.

REQUEST (the user's words, possibly imprecise):
{request}

SLICE: {slice_desc}
EXPECTED (user's ground truth): {expected}
ACTUAL (your current measure returned): {actual}

CURRENT MEASURE:
```dax
{candidate}
```

CONVERSATION SO FAR:
{transcript}

{_SCHEMA_BLOCK.format(model_schema=model_schema)}

Decide between two responses:
1. If you can confidently see the fix (wrong aggregation, missing/extra filter, context-transition issue,
   wrong grain, sign, etc.), return ONLY a corrected `dax` code block — it will be re-tested automatically.
2. If the gap comes from genuine ambiguity in the request (you cannot know the user's intent), DO NOT
   guess and DO NOT output any dax. Instead ask the user ONE short, specific question that would resolve
   it — phrased so the answer pins down the requirement (e.g. "Should this include tax?", "Year-over-year
   vs the same period last year?", "Across all months in the year, or only the selected month?").
Choose the response that most efficiently converges on the correct measure."""


def build_calibrate_refine_prompt(
    model_schema: str, request: str, slice_desc: str, expected: str, candidate: str, refine: str
) -> str:
    """Refine an already-correct measure (perf/readability/rule tweak) while keeping the calibrated value."""
    return f"""\
The DAX measure below already returns the correct value ({expected}) at the slice ({slice_desc}).
The user now wants to refine it: {refine}

Apply the requested change and return a `dax` code block. The revised measure MUST still return {expected}
at that slice — it will be re-tested. If the change would genuinely alter the value at that slice (e.g.
"exclude tax" really changes the number), do NOT output dax; instead say so in one line and ask the user to
confirm the new correct value.

ORIGINAL REQUEST:
{request}

CURRENT MEASURE:
```dax
{candidate}
```

{_SCHEMA_BLOCK.format(model_schema=model_schema)}"""


# Convenience map so a capability/dispatcher can look up the builder by action id.
PROMPT_BUILDERS = {
    "generate": build_generate_prompt,
    "explain": build_explain_prompt,
    "optimize": build_optimize_prompt,
}
