"""
OpenAI-compatible LLM provider.

Talks to any endpoint that speaks the OpenAI Chat Completions API (OpenAI itself, Azure-OpenAI, local
servers like Ollama/LM Studio, vLLM, etc.) via the `openai` SDK. `base_url` selects the endpoint. The
import is lazy, mirroring `claude.py`. Here the system prompt is the first message in the list (OpenAI
has no separate `system=` argument).
"""

from __future__ import annotations

from typing import Any, Iterator, cast

from .base import ChatMessage

_DEFAULT_MAX_TOKENS = 16000


def _max_tokens(opts: dict[str, object]) -> int:
    value = opts.get("max_tokens", _DEFAULT_MAX_TOKENS)
    return int(value) if isinstance(value, (int, float, str)) else _DEFAULT_MAX_TOKENS


class OpenAICompatProvider:
    def __init__(self, api_key: str, model: str, base_url: str = "") -> None:
        from openai import OpenAI  # lazy

        self._client = OpenAI(api_key=api_key, base_url=base_url or None)
        self.model = model

    @staticmethod
    def _to_messages(system: str, messages: list[ChatMessage]) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if system:
            out.append({"role": "system", "content": system})
        out.extend({"role": m.role, "content": m.content} for m in messages)
        return out

    @staticmethod
    def _extra_body(opts: dict[str, object]) -> dict[str, Any]:
        """Map known cross-provider options onto vendor extra_body fields. `enable_thinking` controls
        Qwen's (DashScope) hybrid thinking mode — sending False keeps simple replies fast; other
        OpenAI-compatible endpoints ignore unknown body keys."""
        extra: dict[str, Any] = {}
        if "enable_thinking" in opts:
            extra["enable_thinking"] = bool(opts["enable_thinking"])
        return extra

    def complete(self, system: str, messages: list[ChatMessage], **opts: object) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=cast(Any, self._to_messages(system, messages)),
            max_tokens=_max_tokens(opts),
            extra_body=self._extra_body(opts) or None,
        )
        return (resp.choices[0].message.content or "") if resp.choices else ""

    def stream(self, system: str, messages: list[ChatMessage], **opts: object) -> Iterator[str]:
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=cast(Any, self._to_messages(system, messages)),
            max_tokens=_max_tokens(opts),
            extra_body=self._extra_body(opts) or None,
            stream=True,
        )
        for chunk in cast(Any, stream):
            # some OpenAI-compatible providers (e.g. Doubao) send a final chunk with empty `choices`
            # carrying only usage stats — guard against it instead of indexing [0] blindly.
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
