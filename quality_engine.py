# quality_engine.py
"""Lightweight Quality Engine (0..100) for a symbol based on price/volume behavior.

It is intentionally simple and explainable:
- lower volatility -> better
- stable volume (lower variation) -> better
- enough data points -> required

Used by Dashboard / Signals as a quick quality layer.
"""

from __future__ import annotations

import math
import pandas as pd


def quality_score(df: pd.DataFrame) -> float:
    """Return 0..100 quality score."""
    if df is None or df.empty:
        return 0.0

    d = df.copy()
    # accept both Close and close
    close_col = "Close" if "Close" in d.columns else ("close" if "close" in d.columns else None)
    vol_col = "Volume" if "Volume" in d.columns else ("volume" if "volume" in d.columns else None)
    if close_col is None:
        return 0.0

    close = pd.to_numeric(d[close_col], errors="coerce").dropna()
    if len(close) < 50:
        return 0.0

    rets = close.pct_change().dropna()
    vol = float(rets.std() or 0.0)
    # normalize: 0.00..0.08 typical
    vol_penalty = min(1.0, vol / 0.06)

    volume_penalty = 0.5
    if vol_col is not None:
        vv = pd.to_numeric(d[vol_col], errors="coerce").dropna()
        if len(vv) >= 30:
            cv = float(vv.std() / (vv.mean() or 1.0))
            # CV typical 0..2
            volume_penalty = min(1.0, cv / 1.5)

    # score: higher is better
    raw = 100.0 * (1.0 - 0.65 * vol_penalty - 0.35 * volume_penalty)
    raw = max(0.0, min(100.0, raw))
    return round(raw, 1)


def quality_label(score: float) -> str:
    try:
        s = float(score)
    except Exception:
        s = 0.0
    if s >= 80:
        return "ممتاز"
    if s >= 65:
        return "جيد"
    if s >= 50:
        return "متوسط"
    return "ضعيف"
