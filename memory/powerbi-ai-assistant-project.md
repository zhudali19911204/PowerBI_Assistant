---
name: powerbi-ai-assistant-project
description: "What the PowerBI AI Assistant project is — goals, phasing, MVP scope, environment, stack"
metadata: 
  node_type: memory
  type: project
  originSessionId: e80f40ac-f90a-4270-8df9-75af5b2a0958
---

A tool to AI-assist four Power BI pain points: data cleaning (Power Query/M), data modeling (star/snowflake), **DAX measures**, and dashboard design.

- **Phasing**: Phase 1 MVP = DAX assistant (generate / explain / optimize). Phase 2 = M cleaning + modeling. Phase 3 = dashboard design.
- **Environment constraint**: Power BI **Desktop only** (no Premium/Fabric) → relies on pbix/PBIP text formats + the local Analysis Services engine, not cloud XMLA writeback.
- **Form factor**: standalone Python desktop/web app (Streamlit for MVP), decoupled from Power BI.
- **Stack**: Python 3.11+, replaceable LLM layer (default Claude via `LLMProvider` abstraction), pbixray to read .pbix, pyadomd for live local-AS `EVALUATE`.
- **Architecture**: four cross-cutting abstractions reused across all phases — `LLMProvider`, `ContextSource`, `Capability`/`Action`, `Artifact`. Adding a phase = new `Capability` subclass + `register()`, UI auto-renders.
- Full plan: `docs/DEVELOPMENT_PLAN.md`. DAX knowledge assets: `.claude/skills/dax-expert/` (knowledge base) and `powerbi_ai_assistant/dax/prompts.py` (shipped compressed version).

See [[live-evaluate-validation-is-required]] for the key quality decision, and [[dax-skill-eval-workflow]] for how the skill is benchmarked/improved.
