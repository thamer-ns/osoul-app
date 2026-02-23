# data_normalizer.py
"""Shared normalization helpers for OHLCV.

The project had duplicated normalization logic in several places.
This module centralizes it to keep charts, indicators, and backtests consistent.

Fail-safe behavior:
- If df is None/empty or cannot be normalized -> returns empty DataFrame.
"""

from __future__ import annotations

import pandas as pd


def ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure DatetimeIndex, drop NaT/duplicates, sort."""
    if df is None or df.empty:
        return pd.DataFrame()

    d = df.copy()

    # If there is a date-like column, set it as index
    for c in ["date", "Date", "datetime", "Datetime", "time", "Time", "timestamp", "Timestamp"]:
        if c in d.columns:
            d[c] = pd.to_datetime(d[c], errors="coerce")
            d = d.dropna(subset=[c])
            d = d.sort_values(c)
            d = d.set_index(c)
            break

    if not isinstance(d.index, pd.DatetimeIndex):
        try:
            d.index = pd.to_datetime(d.index, errors="coerce")
        except Exception:
            return pd.DataFrame()

    d = d[~pd.isna(d.index)]
    d = d[~d.index.duplicated(keep="last")]
    try:
        d = d.sort_index()
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at data_normalizer.py:42')
    return d


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize OHLCV columns to Open/High/Low/Close/Volume and ensure datetime index."""
    if df is None or df.empty:
        return pd.DataFrame()

    # Reuse the robust normalizer already used by the market data layer
    try:
        from market_data import _normalize_ohlcv_columns  # type: ignore
        out = _normalize_ohlcv_columns(df)
        if out is None or out.empty:
            return pd.DataFrame()
        return out
    except Exception:
        # Safe fallback: basic normalization
        d = df.copy()
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        d.columns = [str(c) for c in d.columns]
        lower = {c.lower(): c for c in d.columns}
        def pick(*names):
            for n in names:
                if n in d.columns:
                    return n
                if n.lower() in lower:
                    return lower[n.lower()]
            return None
        o = pick("Open","open")
        h = pick("High","high")
        l = pick("Low","low")
        c = pick("Close","close","Adj Close","adj close","adjclose")
        v = pick("Volume","volume","vol")
        if c is None:
            return pd.DataFrame()
        if o is None: d["Open"] = d[c]; o = "Open"
        if h is None: d["High"] = d[c]; h = "High"
        if l is None: d["Low"] = d[c]; l = "Low"
        if v is None: d["Volume"] = 0.0; v = "Volume"
        out = d.rename(columns={o:"Open", h:"High", l:"Low", c:"Close", v:"Volume"})
        for col in ["Open","High","Low","Close","Volume"]:
            out[col] = pd.to_numeric(out[col], errors="coerce")
        out = out.dropna(subset=["Open","High","Low","Close"])
        return ensure_datetime_index(out)
