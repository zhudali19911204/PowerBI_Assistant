"""
Streamlit entry point.

Run from the repository root:

    streamlit run powerbi_ai_assistant/app/main.py

The model/provider/key is configured by the user in the sidebar settings panel (no .env required).
From M7 onward the body will iterate the registered `Capability` objects and render one tab each.
"""

from __future__ import annotations

import streamlit as st

# Streamlit runs this file as __main__ (a script, not a package module), so this must be an
# absolute import — a relative `from .components` would fail with "no known parent package".
# components.py is then loaded as a package module, so ITS relative imports work fine.
from powerbi_ai_assistant.app.components import (
    ensure_capabilities,
    render_capabilities,
    render_model_source_sidebar,
    render_settings_entry,
)
from powerbi_ai_assistant.app.theme import hero, inject_theme

st.set_page_config(page_title="PowerBI AI Assistant", page_icon="📊", layout="wide")
inject_theme()

# Register phase-1 capabilities (idempotent across Streamlit reruns).
ensure_capabilities()

# Sidebar (top-to-bottom): brand + settings gear → model source → field browser.
cfg = render_settings_entry()
ctx = render_model_source_sidebar()

# Main pane.
hero()
render_capabilities(cfg, ctx)

st.divider()
st.caption("方案：docs/DEVELOPMENT_PLAN.md ｜ 规则：CLAUDE.md")
