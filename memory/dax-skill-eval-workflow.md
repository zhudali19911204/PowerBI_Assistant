---
name: dax-skill-eval-workflow
description: How the dax-expert skill / prompts.py are benchmarked and iteratively improved with real cases
metadata: 
  node_type: memory
  type: reference
  originSessionId: e80f40ac-f90a-4270-8df9-75af5b2a0958
---

The DAX "brain" = `.claude/skills/dax-expert/` (long-form knowledge base) + `powerbi_ai_assistant/dax/prompts.py` (shipped compressed version) + live EVALUATE validation. All three are meant to be improved from real usage.

**Benchmark harness (already built, reusable):**
- Workspace: `.claude/skills/dax-expert-workspace/iteration-{N}/eval-{id}/{with_skill,without_skill}/run-1/` each holding `outputs/answer.md`, `grading.json` (fields: `text`/`passed`/`evidence`, plus a `summary` block), `timing.json`. Eval prompt + assertions live in `eval-{id}/eval_metadata.json`.
- Run pairs of subagents (with-skill vs baseline), grade against explicit assertions, then aggregate + view:
  - `cd ~/.claude/skills/skill-creator && PYTHONUTF8=1 python -m scripts.aggregate_benchmark <iter-dir> --skill-name dax-expert`
  - `PYTHONUTF8=1 python eval-viewer/generate_review.py <iter-dir> --skill-name dax-expert --benchmark <iter-dir>/benchmark.json --static <iter-dir>/review.html`
- **Windows gotcha**: always set `PYTHONUTF8=1` (default gbk codec chokes on the JSON).

**Improvement loop:** capture a real failing measure + its schema as a new eval → rerun with the OLD skill/prompts as baseline → improve **skill first, then mirror into prompts.py** to keep them in sync.

Tested finding: top model is already very strong at DAX; the skill's measurable lift is mostly engineering discipline (no redundant guards, no syntax slips). The big architectural lesson is [[live-evaluate-validation-is-required]]. Part of [[powerbi-ai-assistant-project]].
