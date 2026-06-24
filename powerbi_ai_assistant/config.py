"""
Central configuration.

Single source of truth for runtime settings, read from environment / a local `.env` file
(copy `.env.example` to `.env`). Keeping config here means switching LLM provider or toggling live
validation never touches business code — only this file and the `.env`.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- LLM ---
    # Provider is resolved by the LLM factory (M3). Default Claude; switch to an OpenAI-compatible
    # endpoint by setting LLM_PROVIDER=openai_compat plus OPENAI_* below.
    llm_provider: str = "claude"  # "claude" | "openai_compat"
    llm_model: str = "claude-opus-4-8"  # cost-saving alt: "claude-sonnet-4-6"
    anthropic_api_key: str = ""

    # OpenAI-compatible endpoint (optional)
    openai_base_url: str = ""
    openai_api_key: str = ""

    # --- Validation ---
    # When true, generated DAX is run against the local Power BI Desktop AS engine (EVALUATE).
    # When false (or no Desktop running), the app degrades to static checks and labels results
    # as "not run-verified". See DEVELOPMENT_PLAN.md §5.4 / §13.
    enable_live_validation: bool = True

    @property
    def active_api_key(self) -> str:
        """The API key for the currently selected provider."""
        return self.anthropic_api_key if self.llm_provider == "claude" else self.openai_api_key

    @property
    def api_key_configured(self) -> bool:
        return bool(self.active_api_key)


# Import this everywhere: `from powerbi_ai_assistant.config import settings`
settings = Settings()
