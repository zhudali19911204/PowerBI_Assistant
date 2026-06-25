"""DAX capability: generate / explain / optimize measures grounded in the model."""

from .artifact import DaxMeasureArtifact
from .calibrate import CalibrationSession, advance, slice_desc
from .capability import DaxCapability, GenerateAction
from .generate import (
    ParsedMeasure,
    has_dax_block,
    measure_expression,
    parse_dax_blocks,
    parse_measure_response,
    split_measures,
)
from .live_eval import LiveDesktopEvaluator, is_table_expression, validate_measure_set

__all__ = [
    "DaxCapability",
    "GenerateAction",
    "DaxMeasureArtifact",
    "ParsedMeasure",
    "parse_measure_response",
    "parse_dax_blocks",
    "has_dax_block",
    "measure_expression",
    "split_measures",
    "LiveDesktopEvaluator",
    "validate_measure_set",
    "is_table_expression",
    "CalibrationSession",
    "advance",
    "slice_desc",
]
