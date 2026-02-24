"""Thin wrapper around score normalization for backward/forward-compatible imports."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from .score_normalization import normalize_score


def calibrate_score(raw_score: float, *, timeframe: Optional[str] = None, sector: Optional[str] = None, rows: Optional[Iterable[float]] = None) -> Dict[str, Any]:
    return normalize_score(raw_score=raw_score, timeframe=timeframe, sector=sector, rows=rows)
