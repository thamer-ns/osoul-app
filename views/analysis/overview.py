"""Backward-compatible route for the hardened unified overview."""
from __future__ import annotations

from .overview_v4 import TIMEFRAME_LABELS, render_unified_overview

__all__ = ["TIMEFRAME_LABELS", "render_unified_overview"]
