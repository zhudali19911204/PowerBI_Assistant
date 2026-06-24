"""Tests for user-side runtime config persistence and the LLM factory's provider selection."""

from __future__ import annotations

import importlib

import pytest

from powerbi_ai_assistant import runtime_config as rc
from powerbi_ai_assistant.llm import build_provider


def test_default_provider_is_claude():
    cfg = rc.RuntimeConfig()
    assert cfg.provider == "claude"
    assert cfg.model.startswith("claude-")
    assert not cfg.is_ready  # no key yet


def test_save_load_roundtrip(tmp_path, monkeypatch):
    # redirect the config file into a temp dir
    monkeypatch.setattr(rc, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(rc, "CONFIG_FILE", tmp_path / "config.json")

    cfg = rc.RuntimeConfig(provider="claude", model="claude-sonnet-4-6", api_key="sk-test")
    rc.save(cfg, remember_key=True)
    loaded = rc.load()
    assert loaded.model == "claude-sonnet-4-6"
    assert loaded.api_key == "sk-test"
    assert loaded.is_ready


def test_save_without_remember_omits_key(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(rc, "CONFIG_FILE", tmp_path / "config.json")

    rc.save(rc.RuntimeConfig(api_key="sk-secret"), remember_key=False)
    import json

    data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert data["api_key"] == ""


def test_presets_map_to_two_impls_and_carry_base_urls():
    impls = {p.impl for p in rc.PROVIDER_PRESETS}
    assert impls == {"claude", "openai_compat"}
    # named openai-compatible presets pre-fill an endpoint
    assert rc.PRESET_BY_KEY["deepseek"].base_url.startswith("https://api.deepseek.com")
    assert rc.PRESET_BY_KEY["ollama"].base_url.startswith("http://localhost")
    # the custom preset is openai-compatible with a blank base_url for the user to fill
    custom = rc.PRESET_BY_KEY["custom"]
    assert custom.impl == "openai_compat" and custom.base_url == ""


def test_factory_routes_preset_impl():
    # a DeepSeek-style config routes through the openai_compat impl
    cfg = rc.RuntimeConfig(
        preset="deepseek", provider="openai_compat", model="deepseek-chat",
        api_key="", base_url="https://api.deepseek.com/v1",
    )
    # still rejected without a key (validates routing reached the openai branch, not unknown-provider)
    with pytest.raises(ValueError, match="API Key"):
        build_provider(cfg)


def test_factory_requires_key():
    with pytest.raises(ValueError):
        build_provider(rc.RuntimeConfig(provider="claude", model="claude-opus-4-8", api_key=""))


def test_factory_rejects_unknown_provider():
    with pytest.raises(ValueError):
        build_provider(rc.RuntimeConfig(provider="nope", model="x", api_key="sk"))


def test_factory_builds_claude_when_sdk_available():
    pytest.importorskip("anthropic")
    provider = build_provider(
        rc.RuntimeConfig(provider="claude", model="claude-opus-4-8", api_key="sk-fake")
    )
    # structural check: it satisfies the LLMProvider protocol surface
    assert hasattr(provider, "complete") and hasattr(provider, "stream")
    assert provider.model == "claude-opus-4-8"
