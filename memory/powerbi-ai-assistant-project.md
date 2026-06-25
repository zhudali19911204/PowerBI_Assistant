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
- **Stack**: Python 3.11+, replaceable LLM layer (`LLMProvider` abstraction; user configures provider/model in the UI, e.g. Claude or Doubao via OpenAI-compat). Model read/write is **live-only via the open Desktop engine** using Power BI's bundled ADOMD client (read) + downloaded TOM (write) loaded via pythonnet — pbixray/pyadomd are NOT used (static parsing was dropped).
- **Architecture**: four cross-cutting abstractions reused across all phases — `LLMProvider`, `ContextSource`, `Capability`/`Action`, `Artifact`. Adding a phase = new `Capability` subclass + `register()`, UI auto-renders.
- Full plan: `docs/DEVELOPMENT_PLAN.md`. DAX knowledge assets: `.claude/skills/dax-expert/` (knowledge base) and `powerbi_ai_assistant/dax/prompts.py` (shipped compressed version).

Current build state and features: [[dev-progress-2026-06]]. Key quality decision: [[live-evaluate-validation-is-required]]. Skill benchmarking: [[dax-skill-eval-workflow]].
