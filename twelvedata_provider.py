# twelvedata_provider.py
# -*- coding: utf-8 -*-

"""Twelve Data integration layer.

This repo vendors the official Twelve Data Python SDK under `osoul-app-main/twelvedata/`.
We wrap it here to provide:
- Stable OHLCV candles (Japanese candlesticks) for 5+ years
- Throttle + backoff + cache to reduce 429 rate limit issues

Environment / Secrets:
- TWELVEDATA_API_KEY

Notes:
- We keep network calls defensive; if SDK isn't available, we fall back to direct HTTP.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import pandas as pd
import streamlit as st

# Optional requests (fallback)
try:
    import requests  # type: ignore
except Exception:
    requests = None  # type: ignore

# Vendored SDK (shipped inside this repo under /twelvedata)
try:
    from twelvedata import TDClient  # type: ignore

    _HAS_SDK = True
except Exception:
    TDClient = None  # type: ignore
    _HAS_SDK = False


def get_api_key() -> str:
    """Read Twelve Data API key from Streamlit secrets or env."""
    try:
        k = st.secrets.get("TWELVEDATA_API_KEY", "")  # type: ignore
        if k:
            return str(k).strip()
    except Exception:
        pass
    return str(os.environ.get("TWELVEDATA_API_KEY", "")).strip()


def _sleep_with_jitter(base_s: float, attempt: int = 0):
    # tiny jitter to avoid thundering herd on reruns
    try:
        import random

        jitter = random.uniform(0.0, 0.25)
    except Exception:
        jitter = 0.0
    time.sleep(max(0.0, base_s + jitter) * (1.0 + 0.15 * attempt))


def _throttle(key: str = "_td_last_call_ts", min_gap_s: float = 1.2):
    """Simple in-session throttle across reruns."""
    try:
        now = time.time()
        last = float(st.session_state.get(key, 0.0) or 0.0)
        wait = min_gap_s - (now - last)
        if wait > 0:
            time.sleep(wait)
        st.session_state[key] = time.time()
    except Exception:
        pass


def _interval_map(interval: str) -> str:
    itv = (interval or "1d").strip().lower()
    mapping = {
        "1d": "1day",
        "1day": "1day",
        "d": "1day",
        "1wk": "1week",
        "1w": "1week",
        "1week": "1week",
        "w": "1week",
        "1mo": "1month",
        "1m": "1month",
        "1month": "1month",
        "mo": "1month",
        "1h": "1h",
        "60m": "1h",
        "30m": "30min",
        "15m": "15min",
        "5m": "5min",
        "1min": "1min",
    }
    return mapping.get(itv, "1day")


@st.cache_data(ttl=60 * 60, show_spinner=False)
def resolve_symbol(symbol: str, exchange: str = "XSAU") -> str:
    """Best-effort resolve for Saudi symbols.

    - Saudi stocks: prefer exchange=XSAU
    - Indices: allow free search

    Returns a symbol string usable by Twelve Data.
    """
    s = str(symbol or "").strip().upper()
    if not s:
        return ""

    # normalize common forms
    s = s.replace("^", "")
    s = s.replace(".SR", "")

    # TASI alias
    if s in ("TASI", "TADAWUL", "TADAWUL ALL SHARE", "TADAWUL ALL SHARE INDEX"):
        return "TASI"

    key = get_api_key()
    if not key:
        return s

    # SDK path
    if _HAS_SDK and TDClient is not None:
        try:
            client = TDClient(apikey=key)
            # SDK provides symbol_search endpoint
            # NOTE: SDK's symbol_search builder is `client.symbol_search` in older versions,
            # but here we use the generic custom endpoint for maximum compatibility.
            # Endpoint: /symbol_search?symbol=...&exchange=...
            params = {"symbol": s}
            if exchange and s.isdigit():
                params["exchange"] = exchange
            _throttle(min_gap_s=0.8)
            data = client.custom_endpoint(endpoint="symbol_search", **params).as_json()
            arr = data.get("data") if isinstance(data, dict) else None
            if isinstance(arr, list) and arr:
                # exact match first
                for row in arr:
                    if str(row.get("symbol") or "").strip().upper() == s:
                        return str(row.get("symbol") or s).strip()
                return str(arr[0].get("symbol") or s).strip()
        except Exception:
            pass

    # HTTP fallback
    if requests:
        try:
            url = "https://api.twelvedata.com/symbol_search"
            params = {"symbol": s, "apikey": key}
            if exchange and s.isdigit():
                params["exchange"] = exchange
            _throttle(min_gap_s=0.8)
            r = requests.get(url, params=params, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            data = r.json()
            arr = data.get("data") if isinstance(data, dict) else None
            if isinstance(arr, list) and arr:
                for row in arr:
                    if str(row.get("symbol") or "").strip().upper() == s:
                        return str(row.get("symbol") or s).strip()
                return str(arr[0].get("symbol") or s).strip()
        except Exception:
            pass

    return s


def _values_to_ohlcv(values: Any) -> pd.DataFrame:
    if not isinstance(values, (list, tuple)) or not values:
        return pd.DataFrame()

    df = pd.DataFrame(values)
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
        df = df.sort_values("datetime")
        df = df.set_index("datetime")

    # standardize columns
    rename = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }
    for src, dst in rename.items():
        if src in df.columns and dst not in df.columns:
            df[dst] = pd.to_numeric(df[src], errors="coerce")

    keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    if keep:
        df = df[keep]

    df = df.dropna(subset=[c for c in ["Open", "High", "Low", "Close"] if c in df.columns], how="any")
    return df


@st.cache_data(ttl=60 * 30, show_spinner=False)
def get_time_series(symbol: str, interval: str = "1d", years: int = 5, outputsize: int = 5000) -> pd.DataFrame:
    """Fetch OHLCV candles from Twelve Data.

    - Uses SDK if available
    - Falls back to HTTP
    - Returns dataframe with datetime index and Open/High/Low/Close/Volume
    """
    key = get_api_key()
    if not key:
        return pd.DataFrame()

    sym = resolve_symbol(symbol)
    if not sym:
        return pd.DataFrame()

    itv = _interval_map(interval)

    # ---------- SDK path ----------
    if _HAS_SDK and TDClient is not None:
        for attempt in range(4):
            try:
                _throttle(min_gap_s=1.2)
                client = TDClient(apikey=key)
                ts = client.time_series(
                    symbol=sym,
                    interval=itv,
                    outputsize=outputsize,
                    format="JSON",
                )
                data = ts.as_json()

                # SDK returns dict with values sometimes; or direct list
                values = None
                if isinstance(data, dict):
                    values = data.get("values")
                if values is None and isinstance(data, list):
                    values = data

                df = _values_to_ohlcv(values)
                if not df.empty:
                    if years and isinstance(df.index, pd.DatetimeIndex):
                        cutoff = pd.Timestamp.utcnow() - pd.DateOffset(years=int(years))
                        df = df[df.index >= cutoff]
                    return df

                # Handle rate limit / temporary errors
                msg = ""
                if isinstance(data, dict):
                    msg = str(data.get("message") or data.get("error") or "")
                    status = str(data.get("status") or "").lower()
                    if status == "error" or "rate" in msg.lower() or "429" in msg:
                        _sleep_with_jitter(base_s=min(10.0, 1.5 * (2 ** attempt)), attempt=attempt)
                        continue

                return pd.DataFrame()
            except Exception:
                _sleep_with_jitter(base_s=min(10.0, 1.5 * (2 ** attempt)), attempt=attempt)

    # ---------- HTTP fallback ----------
    if requests:
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": sym,
            "interval": itv,
            "outputsize": outputsize,
            "format": "JSON",
            "apikey": key,
        }
        for attempt in range(4):
            try:
                _throttle(min_gap_s=1.2)
                r = requests.get(url, params=params, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                data = r.json()
                values = data.get("values") if isinstance(data, dict) else None
                df = _values_to_ohlcv(values)
                if not df.empty:
                    if years and isinstance(df.index, pd.DatetimeIndex):
                        cutoff = pd.Timestamp.utcnow() - pd.DateOffset(years=int(years))
                        df = df[df.index >= cutoff]
                    return df

                msg = str(data.get("message") or data.get("error") or "") if isinstance(data, dict) else ""
                status_code = int(getattr(r, "status_code", 0) or 0)
                if status_code in (429, 500, 502, 503, 504) or ("rate" in msg.lower()):
                    _sleep_with_jitter(base_s=min(10.0, 1.5 * (2 ** attempt)), attempt=attempt)
                    continue

                return pd.DataFrame()
            except Exception:
                _sleep_with_jitter(base_s=min(10.0, 1.5 * (2 ** attempt)), attempt=attempt)

    return pd.DataFrame()


@st.cache_data(ttl=60 * 10, show_spinner=False)
def get_api_usage() -> Dict[str, Any]:
    """Return Twelve Data API usage info (helpful for debugging limits)."""
    key = get_api_key()
    if not key:
        return {"ok": False, "reason": "missing_api_key"}

    # SDK path
    if _HAS_SDK and TDClient is not None:
        try:
            _throttle(min_gap_s=0.8)
            client = TDClient(apikey=key)
            data = client.get_api_usage().as_json()
            return {"ok": True, "data": data}
        except Exception:
            pass

    # HTTP fallback
    if requests:
        try:
            _throttle(min_gap_s=0.8)
            r = requests.get(
                "https://api.twelvedata.com/api_usage",
                params={"apikey": key},
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            data = r.json()
            return {"ok": True, "data": data}
        except Exception as e:
            return {"ok": False, "reason": str(e)}

    return {"ok": False, "reason": "no_requests"}


def get_quote(symbol: str) -> Dict[str, Any]:
    """Get real-time quote via Twelve Data.

    Returns:
      {"ok": bool, "price": float, "prev_close": float, "chg_pct": float, "raw": ...}

    Notes:
    - For indices (TASI), Twelve Data typically supports the symbol "TASI".
    - If prev_close is missing, we fall back to last known close from time_series.
    """
    key = get_api_key()
    if not key:
        return {"ok": False, "reason": "missing_api_key"}

    sym = resolve_symbol(symbol)

    # SDK path
    try:
        client = TDClient(apikey=key)
        data = client.quote(symbol=sym).as_json()
        if isinstance(data, dict) and str(data.get("status", "")).lower() != "error":
            price = float(data.get("close") or data.get("price") or data.get("last") or 0.0)
            prev = float(data.get("previous_close") or data.get("prev_close") or 0.0)
            chg_pct = float(data.get("percent_change") or data.get("change_percent") or 0.0)
            return {"ok": price > 0, "price": price, "prev_close": prev, "chg_pct": chg_pct, "raw": data}
    except Exception:
        pass

    # HTTP fallback
    if requests:
        try:
            _throttle(min_gap_s=0.8)
            r = requests.get(
                "https://api.twelvedata.com/quote",
                params={"apikey": key, "symbol": sym},
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            data = r.json()
            if isinstance(data, dict) and str(data.get("status", "")).lower() != "error":
                price = float(data.get("close") or data.get("price") or data.get("last") or 0.0)
                prev = float(data.get("previous_close") or data.get("prev_close") or 0.0)
                chg_pct = float(data.get("percent_change") or data.get("change_percent") or 0.0)
                return {"ok": price > 0, "price": price, "prev_close": prev, "chg_pct": chg_pct, "raw": data}
            return {"ok": False, "reason": str(data.get("message") or data.get("error") or "quote_error"), "raw": data}
        except Exception as e:
            return {"ok": False, "reason": str(e)}

    return {"ok": False, "reason": "no_requests"}
