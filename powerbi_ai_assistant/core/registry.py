"""
Capability registry.

A tiny global registry the UI reads to decide what to render. Phases register their capability once
(typically at import time); the UI then iterates `all_capabilities()`. This indirection is what lets
phase 2/3 light up new tabs without touching the app code.
"""

from __future__ import annotations

from .capability import Capability

CAPABILITIES: dict[str, Capability] = {}


def register(cap: Capability) -> None:
    if not cap.id:
        raise ValueError(f"Capability {type(cap).__name__} must set a non-empty `id`")
    if cap.id in CAPABILITIES:
        raise ValueError(f"Capability id already registered: {cap.id!r}")
    CAPABILITIES[cap.id] = cap


def get(cap_id: str) -> Capability:
    return CAPABILITIES[cap_id]


def all_capabilities() -> list[Capability]:
    return list(CAPABILITIES.values())


def clear() -> None:
    """Reset the registry (used by tests)."""
    CAPABILITIES.clear()
