# ai_engine_core/core.py

from __future__ import annotations

import re
from typing import Any, Optional


def _normalize_symbol(symbol: str) -> str:
    """
    Normalize symbol to a consistent internal format.
    - Keep Saudi tickers as-is (e.g. 4161.SR)
    - Strip spaces
    """
    s = str(symbol or "").strip().upper()
    s = re.sub(r"\s+", "", s)
    return s


def _to_float(x: Any, default: Optional[float] = 0.0) -> Optional[float]:
    """
    Safe float conversion used across AI engine.

    - Returns `default` if conversion fails.
    - If default is None -> returns None on failure.
    """
    try:
        if x is None:
            return default
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip()
        if not s:
            return default
        s = s.replace(",", "")
        # handle parentheses negative e.g. "(123.4)"
        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]
        # strip common currency tokens
        s = s.replace("SAR", "").replace("ر.س", "").strip()
        # NaN-like
        if s.lower() in ("nan", "none", "null", "na"):
            return default
        return float(s)
    except Exception:
        return default


def _round2(x: Any, default: float = 0.0) -> float:
    """
    Round to 2 decimals safely.
    """
    v = _to_float(x, None)
    if v is None:
        return float(default)
    try:
        return float(round(v, 2))
    except Exception:
        return float(default)