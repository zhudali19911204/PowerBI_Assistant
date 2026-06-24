"""
User-facing runtime LLM configuration.

The model/provider/key is configured by the **end user in the app UI**, not via `.env`. This module
holds that runtime choice and persists it to a small JSON file under the user's home directory so it
survives restarts. Environment values (`config.Settings`) act only as defaults/fallbacks.

Provider model: there are only two *implementations* (`claude` and `openai_compat`), because those are
the two wire protocols. But almost every third-party or local model — DeepSeek, Moonshot/Kimi, Qwen,
Azure-OpenAI, Ollama, vLLM, OpenRouter — speaks the OpenAI-compatible protocol, so they're all reachable
through `openai_compat` by pointing `base_url` at the right endpoint. `PROVIDER_PRESETS` are friendly
presets over those two implementations (a preset just pre-fills impl + base_url + suggested models); the
final "custom" preset lets the user enter any OpenAI-compatible endpoint.

Security note: if the user opts to remember the key, it is stored in plaintext at
`~/.powerbi_ai_assistant/config.json` (permissions tightened to 0600 where the OS supports it).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import settings

CONFIG_DIR = Path.home() / ".powerbi_ai_assistant"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass(frozen=True)
class ProviderPreset:
    key: str               # stable id stored in config
    label: str             # shown in the dropdown
    impl: str              # "claude" | "openai_compat" — which provider class the factory builds
    base_url: str = ""     # default endpoint for openai_compat presets
    models: tuple[str, ...] = ()  # suggested model ids (user can still type a custom one)


# Order matters — this is the dropdown order.
PROVIDER_PRESETS: list[ProviderPreset] = [
    ProviderPreset("claude", "Claude (Anthropic)", "claude", "",
                   ("claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5")),
    ProviderPreset("openai", "OpenAI", "openai_compat", "https://api.openai.com/v1",
                   ("gpt-4o", "gpt-4o-mini", "gpt-4.1")),
    ProviderPreset("deepseek", "DeepSeek", "openai_compat", "https://api.deepseek.com/v1",
                   ("deepseek-chat", "deepseek-reasoner")),
    ProviderPreset("moonshot", "Moonshot (Kimi)", "openai_compat", "https://api.moonshot.cn/v1",
                   ("moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k")),
    ProviderPreset("qwen", "通义千问 (DashScope)", "openai_compat",
                   "https://dashscope.aliyuncs.com/compatible-mode/v1",
                   ("qwen-plus", "qwen-max", "qwen-turbo")),
    ProviderPreset("ollama", "Ollama 本地", "openai_compat", "http://localhost:11434/v1",
                   ("llama3.1", "qwen2.5", "mistral")),
    ProviderPreset("openrouter", "OpenRouter", "openai_compat", "https://openrouter.ai/api/v1",
                   ("openai/gpt-4o", "anthropic/claude-sonnet-4.5")),
    ProviderPreset("custom", "自定义 (OpenAI 兼容)", "openai_compat", "", ()),
]
PRESET_BY_KEY: dict[str, ProviderPreset] = {p.key: p for p in PROVIDER_PRESETS}


@dataclass
class RuntimeConfig:
    preset: str = "claude"      # which ProviderPreset the user picked (UI label source)
    provider: str = "claude"    # the impl the factory builds: "claude" | "openai_compat"
    model: str = "claude-opus-4-8"
    api_key: str = ""
    base_url: str = ""          # only used by openai_compat

    @property
    def is_ready(self) -> bool:
        return bool(self.api_key) and bool(self.model) and bool(self.provider)


def _defaults() -> RuntimeConfig:
    provider = settings.llm_provider
    preset = "claude" if provider == "claude" else "openai"
    return RuntimeConfig(
        preset=preset,
        provider=provider,
        model=settings.llm_model,
        api_key=settings.active_api_key,
        base_url=settings.openai_base_url,
    )


def load() -> RuntimeConfig:
    """Load saved config, falling back to environment defaults for any missing field."""
    cfg = _defaults()
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            for fld in ("preset", "provider", "model", "api_key", "base_url"):
                value = data.get(fld)
                if value:
                    setattr(cfg, fld, value)
        except (json.JSONDecodeError, OSError):
            pass  # corrupt/unreadable file → just use defaults
    return cfg


def save(cfg: RuntimeConfig, remember_key: bool = True) -> Path:
    """Persist config to the user's home dir. When remember_key is False the key is not written."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = asdict(cfg)
    if not remember_key:
        data["api_key"] = ""
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass  # best-effort on platforms without POSIX perms
    return CONFIG_FILE
