---
name: mquery-assistant-interaction-preference
description: "How the user wants to work with the Power Query (M) assistant: they drive in Desktop, AI is an on-demand snippet helper for hard steps"
metadata:
  node_type: memory
  type: feedback
---

For the phase-2 Power Query (M) assistant, the user chose interaction model **"我为主 + AI 补难点"** (2026-06-25): they point-and-click in Power Query Editor themselves for most steps, and only call the AI for the specific step they're stuck on (the M they can't write / a function they can't recall). They explicitly do NOT want the assistant to own/drive the whole query.

**Why:** Many cleaning ops are faster to do by hand in Desktop's editor than to describe in words; the user feels a tension between step-by-step AI help and "some things I do faster myself." The resolution is to treat Desktop's editor and the AI as complementary, with the human as the primary driver.

**How to apply:** Design the M assistant as a lightweight, on-demand **snippet/patch helper**, not a full-pipeline generator:
- Make **"🔄 从 Desktop 同步"** central (not optional): re-read the query's current *applied* M from the engine so the AI is always grounded in the user's latest real state. (User must `关闭并应用` in Desktop first; we read the engine's partition QueryDefinition.)
- Let the user ask for just **the one step they're stuck on**; AI returns that step (verified by appending onto the current applied M and running the refresh round-trip [[mquery-refresh-verification]]).
- Offer output as either (i) just the new step/expression to paste at the right place, or (ii) the full `let … in` for whole-query replace — user picks per use.

Still-open decisions (user is reviewing priorities, hasn't committed scope): the 3 pain points are 多查询合并/追加 (multi-query inputs), 增量补片段对话 (this preference), and 目标导向清洗 (result/example-driven, like DAX calibration). See [[dev-progress-2026-06]]. Recall the user's general style: [[working-style-confirm-and-honest]].
