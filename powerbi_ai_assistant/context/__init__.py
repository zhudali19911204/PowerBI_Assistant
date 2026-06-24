"""Model context layer — load and represent the Power BI model (live Desktop connection only)."""

from .base import Column, ContextSource, Measure, ModelContext, Relationship
from .live_source import (
    DesktopInstance,
    LiveDesktopSource,
    find_adomd_dll,
    find_instances,
)

__all__ = [
    "Column",
    "Relationship",
    "Measure",
    "ModelContext",
    "ContextSource",
    "LiveDesktopSource",
    "DesktopInstance",
    "find_instances",
    "find_adomd_dll",
]
