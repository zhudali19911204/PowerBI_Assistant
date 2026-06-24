"""LLM abstraction layer — provider-agnostic interface + factory."""

from .base import ChatMessage, LLMProvider, user
from .factory import build_provider

__all__ = ["ChatMessage", "LLMProvider", "user", "build_provider"]
