"""M0 smoke tests: the skeleton imports and the core assets are wired."""

from __future__ import annotations


def test_config_imports():
    from powerbi_ai_assistant.config import settings

    assert settings.llm_provider in {"claude", "openai_compat"}
    assert settings.llm_model  # non-empty default
    # property helpers work without raising
    assert isinstance(settings.api_key_configured, bool)


def test_dax_prompts_wired():
    from powerbi_ai_assistant.dax import prompts as p

    assert "NESTED-ITERATOR TRAP" in p.DAX_SYSTEM_PROMPT
    assert set(p.PROMPT_BUILDERS) == {"generate", "explain", "optimize"}
    out = p.build_generate_prompt("TABLE Sales[Amount]", "year over year sales %")
    assert "MODEL SCHEMA" in out and "year over year" in out
