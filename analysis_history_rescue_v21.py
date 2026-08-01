"""Bounded Yahoo Chart rescue for cold analysis-history starts.

The normal market router remains authoritative.  This module is used only when
that routed call returns no candles inside the interactive budget.  It performs
one direct, bounded request to Yahoo's chart endpoint, validates OHLCV geometry
and returns an auditable frame without changing live-price priority.
"""
from __future__ import annotations

import logging
import math
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import pandas as pd

try:
    import requests
except Exception:  # pragma: no cover - optional in constrained environments
    requests = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)
_THREAD_LOCAL = threading.local()
_ALLOWED_SYMBOL = re.compile(r"^[A-Z0-9.^=_\-]{1,40}$")
_TIMEOUT = (0.75, 3.25)


def _session() -> Any:
    if requests is None:
        return None
    current = getattr(_THREAD_LOCAL, "session", None)
    if current is None:
        current = requests.Session()
        current.headers.update(
            {
                "User-Agent": "Osoli/21.0 analysis-history-rescue",
                "Accept": "application/json,text/plain,*/*",
            }
        )
        _THREAD_LOCAL.session = current
    return current


def _symbol(value: Any) -> str:
    raw = str(value or "").strip().upper().replace("TADAWUL:", "")
    if raw.isdigit():
        raw = f"{raw}.SR"
    return raw if _ALLOWED_SYMBOL.fullmatch(raw) else ""


def _interval_policy(interval: str) -> tuple[str, str, str | None]:
    raw = str(interval or "1d").strip().lower()
    normalized = {
        "60m": "1h",
        "60min": "1h",
        "1w": "1wk",
        "week": "1wk",
        "weekly": "1wk",
        "month": "1mo",
        "monthly": "1mo",
        "240m": "4h",
    }.get(raw, raw)
    if normalized == "4h":
        return normalized, "60m", "4h"
    if normalized == "1wk":
        return normalized, "1d", "W-THU"
    if normalized == "1mo":
        return normalized, "1d", "ME"
    yahoo_interval = "60m" if normalized == "1h" else normalized
    return normalized, yahoo_interval, None


def _range_policy(period: str | None, interval: str) -> str:
    normalized = str(period or "").strip().lower()
    if interval == "1m":
        return "7d"
    if interval in {"2m", "5m", "15m", "30m"}:
        return "60d"
    if interval in {"1h", "4h"}:
        return "2y"
    accepted = {
        "1d",
        "5d",
        "1mo",
        "3mo",
        "6mo",
        "1y",
        "2y",
        "5y",
        "10y",
        "ytd",
        "max",
    }
    if normalized in accepted:
        return normalized
    match = re.fullmatch(r"(\d+)y", normalized)
    if match:
        years = int(match.group(1))
        if years <= 1:
            return "1y"
        if years <= 2:
            return "2y"
        if years <= 5:
            return "5y"
        if years <= 10:
            return "10y"
        return "max"
    return "5y"


def _minimum_rows(interval: str) -> int:
    if interval == "1mo":
        return 24
    if interval == "1wk":
        return 52
    if interval == "1d":
        return 60
    return 80


def _finite_series(values: Any, size: int) -> pd.Series:
    data = list(values) if isinstance(values, list) else []
    if len(data) < size:
        data.extend([None] * (size - len(data)))
    return pd.to_numeric(pd.Series(data[:size]), errors="coerce")


def _parse(payload: Any) -> tuple[pd.DataFrame, str]:
    chart = payload.get("chart") if isinstance(payload, dict) else None
    if not isinstance(chart, dict):
        return pd.DataFrame(), "invalid_payload"
    if chart.get("error"):
        return pd.DataFrame(), "provider_error"
    results = chart.get("result")
    if not isinstance(results, list) or not results:
        return pd.DataFrame(), "missing_result"
    result = results[0] if isinstance(results[0], dict) else {}
    timestamps = result.get("timestamp")
    if not isinstance(timestamps, list) or not timestamps:
        return pd.DataFrame(), "missing_timestamps"
    indicators = result.get("indicators")
    quotes = indicators.get("quote") if isinstance(indicators, dict) else None
    row = quotes[0] if isinstance(quotes, list) and quotes else {}
    if not isinstance(row, dict):
        return pd.DataFrame(), "missing_ohlcv"

    size = len(timestamps)
    index = pd.to_datetime(
        pd.to_numeric(pd.Series(timestamps), errors="coerce"),
        unit="s",
        utc=True,
        errors="coerce",
    )
    frame = pd.DataFrame(
        {
            "Open": _finite_series(row.get("open"), size),
            "High": _finite_series(row.get("high"), size),
            "Low": _finite_series(row.get("low"), size),
            "Close": _finite_series(row.get("close"), size),
            "Volume": _finite_series(row.get("volume"), size).fillna(0.0),
        },
        index=index,
    )
    frame = frame[~frame.index.isna()]
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"])
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    if frame.empty:
        return pd.DataFrame(), "empty_after_normalization"

    finite = frame[["Open", "High", "Low", "Close"]].applymap(
        lambda value: math.isfinite(float(value)) and float(value) > 0
    )
    frame = frame[finite.all(axis=1)]
    geometry = (
        (frame["High"] >= frame[["Open", "Close"]].max(axis=1))
        & (frame["Low"] <= frame[["Open", "Close"]].min(axis=1))
        & (frame["High"] >= frame["Low"])
        & (frame["Volume"] >= 0)
    )
    frame = frame[geometry]
    return (frame, "") if not frame.empty else (pd.DataFrame(), "invalid_geometry")


def _resample(frame: pd.DataFrame, rule: str | None) -> pd.DataFrame:
    if frame.empty or not rule:
        return frame
    output = pd.DataFrame(
        {
            "Open": frame["Open"].resample(rule).first(),
            "High": frame["High"].resample(rule).max(),
            "Low": frame["Low"].resample(rule).min(),
            "Close": frame["Close"].resample(rule).last(),
            "Volume": frame["Volume"].fillna(0.0).resample(rule).sum(),
        }
    )
    return output.dropna(subset=["Open", "High", "Low", "Close"])


def fetch_yahoo_history_rescue(
    symbol: str,
    *,
    period: str | None,
    interval: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return a validated history frame and safe diagnostics after one request."""
    resolved = _symbol(symbol)
    normalized, yahoo_interval, resample_rule = _interval_policy(interval)
    yahoo_range = _range_policy(period, normalized)
    diagnostic: dict[str, Any] = {
        "source": "yahoo",
        "adapter": "chart_api_v21",
        "symbol": resolved,
        "interval": normalized,
        "range": yahoo_range,
        "ok": False,
        "reason": "",
        "elapsed_ms": 0,
    }
    if not resolved:
        diagnostic["reason"] = "invalid_symbol"
        return pd.DataFrame(), diagnostic
    session = _session()
    if session is None:
        diagnostic["reason"] = "requests_unavailable"
        return pd.DataFrame(), diagnostic

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(resolved, safe='')}"
    started = time.perf_counter()
    try:
        response = session.get(
            url,
            params={
                "range": yahoo_range,
                "interval": yahoo_interval,
                "includePrePost": "false",
                "events": "div,splits",
            },
            timeout=_TIMEOUT,
            allow_redirects=True,
        )
        diagnostic["elapsed_ms"] = round(
            (time.perf_counter() - started) * 1000
        )
        if int(response.status_code) != 200:
            diagnostic["reason"] = f"http_{int(response.status_code)}"
            return pd.DataFrame(), diagnostic
        try:
            payload = response.json()
        except ValueError:
            diagnostic["reason"] = "invalid_json"
            return pd.DataFrame(), diagnostic
    except Exception as exc:
        diagnostic["elapsed_ms"] = round(
            (time.perf_counter() - started) * 1000
        )
        diagnostic["reason"] = type(exc).__name__.lower()
        return pd.DataFrame(), diagnostic

    frame, reason = _parse(payload)
    if frame.empty:
        diagnostic["reason"] = reason or "empty"
        return pd.DataFrame(), diagnostic
    frame = _resample(frame, resample_rule)
    minimum = _minimum_rows(normalized)
    if len(frame) < minimum:
        diagnostic["reason"] = "insufficient_rows"
        diagnostic["rows"] = int(len(frame))
        return pd.DataFrame(), diagnostic

    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    lineage = {
        "source": "yahoo",
        "adapter": "chart_api_v21",
        "symbol": resolved,
        "interval": normalized,
        "fetched_interval": yahoo_interval,
        "period": yahoo_range,
        "rows": int(len(frame)),
        "start": str(frame.index.min()),
        "end": str(frame.index.max()),
        "fetched_at": fetched_at,
        "quality_score": 100,
        "is_stale": False,
        "cold_start_rescue": True,
    }
    frame.attrs["source"] = "yahoo"
    frame.attrs["data_lineage"] = lineage
    diagnostic.update(
        {
            "ok": True,
            "reason": "",
            "rows": int(len(frame)),
            "fetched_at": fetched_at,
        }
    )
    LOGGER.info(
        "Yahoo history rescue succeeded for %s %s with %s rows",
        resolved,
        normalized,
        len(frame),
    )
    return frame, diagnostic


__all__ = ["fetch_yahoo_history_rescue"]
