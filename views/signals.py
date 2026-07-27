"""Backward-compatible route for the v4 portfolio signal center."""
from __future__ import annotations

from .signals_v4 import (
    TIMEFRAMES,
    _decision_fields,
    _entry_text,
    _recommendation_kind,
    _safe_number,
    view_signals,
)

__all__ = [
    "TIMEFRAMES",
    "_decision_fields",
    "_entry_text",
    "_recommendation_kind",
    "_safe_number",
    "view_signals",
]
