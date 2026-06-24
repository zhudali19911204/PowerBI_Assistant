"""
LLM factory — the single switch that turns a `RuntimeConfig` into an `LLMProvider`.

This is the only place that knows about concrete providers, so the rest of the product depends solely
on the `LLMProvider` protocol. Switching vendor is a config change in the UI; no business code changes.
"""

from __future__ import annotations

from ..net import enable_os_trust_store
from ..runtime_config import RuntimeConfig
from .base import LLMProvider


def build_provider(cfg: RuntimeConfig) -> LLMProvider:
    if not cfg.api_key:
        raise ValueError("尚未配置 API Key（请在设置面板填写）")
    if not cfg.model:
        raise ValueError("尚未选择模型")

    # Trust the OS certificate store before any HTTPS client is created, so requests succeed behind a
    # TLS-inspecting corporate proxy (whose root CA the OS trusts but certifi doesn't). See net.py.
    enable_os_trust_store()

    if cfg.provider == "claude":
        from .claude import ClaudeProvider

        return ClaudeProvider(api_key=cfg.api_key, model=cfg.model)

    if cfg.provider == "openai_compat":
        from .openai_compat import OpenAICompatProvider

        return OpenAICompatProvider(api_key=cfg.api_key, model=cfg.model, base_url=cfg.base_url)

    raise ValueError(f"未知的 provider: {cfg.provider!r}")
