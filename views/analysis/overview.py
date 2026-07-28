"""Backward-compatible route for the v5 unified overview."""
from __future__ import annotations

from .overview_v5 import TIMEFRAME_LABELS, render_unified_overview

__all__ = ["TIMEFRAME_LABELS", "render_unified_overview"]
