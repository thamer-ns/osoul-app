# ai_engine_core/core.py

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional


def _now_str() -> str:
    """Return a readable timestamp string."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_symbol(symbol: str) -> str:
    """Normalize symbol to a consistent internal format."""
    s = str(symbol or "").strip().upper()
    s = re.sub(r"\s+", "", s)

    # Saudi numeric tickers
    if s.isdigit():
        return f"{s}.SR"

    # common index mapping kept as-is
    return s


def _map_period_from_timeframe(timeframe: str) -> str:
    """Map a UI timeframe to a yfinance-like period (best-effort)."""
    tf = str(timeframe or "1D").upper().strip()
    if tf in ("1H", "60M", "H"):
        return "60d"
    if tf in ("4H", "240M"):
        return "180d"
    if tf in ("1W", "W"):
        return "5y"
    if tf in ("1MO", "1M", "MO"):
        return "10y"
    return "6mo"


def _to_float(x: Any, default: Optional[float] = 0.0) -> Optional[float]:
    """Safe float conversion used across AI engine."""
    try:
        if x is None:
            return default
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip()
        if not s:
            return default
        s = s.replace(",", "")
        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]
        s = s.replace("SAR", "").replace("ر.س", "").strip()
        if s.lower() in ("nan", "none", "null", "na"):
            return default
        return float(s)
    except Exception:
        return default


def _round2(x: Any, default: float = 0.0) -> float:
    """Round to 2 decimals safely."""
    v = _to_float(x, None)
    if v is None:
        return float(default)
    try:
        return float(round(v, 2))
    except Exception:
        return float(default)
