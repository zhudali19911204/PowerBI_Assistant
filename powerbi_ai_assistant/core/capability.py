"""
Capability / Action abstraction — the plugin seam of the whole product.

A `Capability` is a pillar (DAX, cleaning, modeling, dashboard); an `Action` is one thing it can do
(generate / explain / optimize). The UI iterates the registered capabilities and renders them, so a new
phase is added by writing a `Capability` subclass and calling `register()` — no framework or UI change.
Actions take an `ActionRequest` (the user's text + the grounding `ModelContext`) and return an
`ActionResult` (artifacts + explanation).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..context.base import ModelContext
from .artifact import Artifact

if TYPE_CHECKING:  # keep core decoupled from llm at runtime — the annotation is a string
    from ..llm.base import LLMProvider
    from .artifact import MeasureEvaluator


@dataclass
class ActionRequest:
    text: str                       # the user's natural-language input (or a measure to explain/optimize)
    context: ModelContext           # grounding: the real model
    # The LLM to run this action through. Every capability needs one, so it lives on the request
    # (built per-call from the user's runtime config) rather than baked into the registered capability.
    provider: "LLMProvider | None" = None
    # Optional live evaluator (a connected Desktop engine). When present, generated DAX is run-verified
    # and the generate->static->live->repair loop engages; when absent, validation stays static-only.
    evaluator: "MeasureEvaluator | None" = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResult:
    artifacts: list[Artifact] = field(default_factory=list)
    explanation: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


class Action(ABC):
    id: str = ""        # e.g. "generate"
    label: str = ""     # human label for the UI, e.g. "生成"

    @abstractmethod
    def run(self, req: ActionRequest) -> ActionResult:
        ...


class Capability(ABC):
    id: str = ""        # e.g. "dax"
    name: str = ""      # human label for the tab, e.g. "DAX 助手"

    @abstractmethod
    def actions(self) -> list[Action]:
        ...
