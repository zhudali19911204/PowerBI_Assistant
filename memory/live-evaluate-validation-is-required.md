---
name: live-evaluate-validation-is-required
description: "Why live DAX EVALUATE validation is a hard phase-1 requirement, not optional"
metadata: 
  node_type: memory
  type: project
  originSessionId: e80f40ac-f90a-4270-8df9-75af5b2a0958
---

In the dax-expert skill benchmark (3 rounds, with-skill vs without-skill), on the hardest round both configs — top model, with and without the skill — produced a measure (inventory turnover) that **compiles, explains itself coherently, but is semantically wrong**: a nested iterator `AVERAGEX(VALUES('Date'[Date]), SUMX('Inventory', ...))` missing a `CALCULATE`, so no context transition happens and it returns the period total instead of a daily average. Neither the skill nor the model's self-review caught it.

**Why:** static generation + LLM self-check is not reliable for deep nested context-transition bugs. Only actually running the measure (`DEFINE MEASURE ... EVALUATE ROW(...)` against the running Desktop's local AS via pyadomd) catches "looks right, runs wrong."

**How to apply:** keep live EVALUATE validation as a phase-1 core capability, not an optional enhancement. When no Desktop is running, degrade to static checks but explicitly label results "not run-verified" — never present unverified DAX as verified. The trap is now documented in the skill (`references/context-and-evaluation.md` §11) and `prompts.py`. Part of [[powerbi-ai-assistant-project]].
