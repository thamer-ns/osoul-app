"""Resilient, auditable market-data adapters for Osoli v5.

Supported optional providers:
- Twelve Data (existing integration)
- Financial Modeling Prep (FMP)
- EODHD
- Alpha Vantage

Yahoo/yfinance remains outside this module as the final compatibility fallback
owned by ``market_data.py``.  Every adapter is defensive: no key means no call,
all frames are normalized, malformed candles are rejected, and provider
attempts are recorded in dataframe lineage instead of being silently hidden.
"""
from __future__ import annotations

import logging
import math
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Callable, Iterable

import pandas as pd

try:
    import requests
except Exception:  # pragma: no cover - optional in constrained deployments
    requests = None  # type: ignore[assignment]

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)
_DEFAULT_ORDER = ("twelvedata", "fmp", "eodhd", "alphavantage")
_SECRET_NAMES = {
    "fmp": "FMP_API_KEY",
    "eodhd": "EODHD_API_KEY",
    "alphavantage": "ALPHAVANTAGE_API_KEY",
    "twelvedata": "TWELVEDATA_API_KEY",
}
_MAX_RETRIES = 3
_MIN_ROWS = 20
_SESSION = requests.Session() if requests is not None else None
if _SESSION is not None:
    _SESSION.headers.update(
        {
            "User-Agent": "Osoli/5.0 market-data-fusion",
            "Accept": "application/json,text/plain,*/*",
        }
    )


@dataclass(slots=True)
class ProviderAttempt:
    provider: str
    ok: bool
    reason: str = ""
    rows: int = 0
    resolved_symbol: str = ""
    elapsed_ms: int = 0
    quality_score: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "ok": self.ok,
            "reason": self.reason,
            "rows": self.rows,
            "resolved_symbol": self.resolved_symbol,
            "elapsed_ms": self.elapsed_ms,
            "quality_score": self.quality_score,
        }


@dataclass(slots=True)
class CircuitState:
    failures: int = 0
    opened_until: float = 0.0
    last_error: str = ""


_CIRCUITS: dict[str, CircuitState] = {}
_CIRCUIT_LOCK = threading.RLock()


def _secret(name: str) -> str:
    if st is not None:
        try:
            value = st.secrets.get(name, "")  # type: ignore[union-attr]
            if value:
                return str(value).strip()
        except Exception:
            LOGGER.debug("Streamlit secret lookup failed for %s", name, exc_info=True)
    return str(os.getenv(name, "") or "").strip()


def configured_provider_order() -> list[str]:
    raw = _secret("MARKET_DATA_PROVIDER_ORDER") or os.getenv(
        "MARKET_DATA_PROVIDER_ORDER", ""
    )
    requested = [item.strip().lower() for item in str(raw).split(",") if item.strip()]
    order = requested or list(_DEFAULT_ORDER)
    output: list[str] = []
    for provider in order:
        if provider in _DEFAULT_ORDER and provider not in output:
            output.append(provider)
    for provider in _DEFAULT_ORDER:
        if provider not in output:
            output.append(provider)
    return output


def provider_status() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with _CIRCUIT_LOCK:
        for provider in configured_provider_order():
            state = _CIRCUITS.get(provider, CircuitState())
            rows.append(
                {
                    "provider": provider,
                    "configured": bool(_secret(_SECRET_NAMES[provider])),
                    "circuit_open": state.opened_until > time.time(),
                    "failures": state.failures,
                    "last_error": state.last_error,
                }
            )
    return rows


def _circuit_allows(provider: str) -> bool:
    with _CIRCUIT_LOCK:
        state = _CIRCUITS.setdefault(provider, CircuitState())
        if state.opened_until and state.opened_until <= time.time():
            state.opened_until = 0.0
            state.failures = max(0, state.failures - 1)
        return state.opened_until <= time.time()


def _circuit_success(provider: str) -> None:
    with _CIRCUIT_LOCK:
        state = _CIRCUITS.setdefault(provider, CircuitState())
        state.failures = 0
        state.opened_until = 0.0
        state.last_error = ""


def _circuit_failure(provider: str, reason: str) -> None:
    with _CIRCUIT_LOCK:
        state = _CIRCUITS.setdefault(provider, CircuitState())
        state.failures += 1
        state.last_error = str(reason)[:160]
        if state.failures >= 3:
            state.opened_until = time.time() + min(900.0, 30.0 * (2 ** min(4, state.failures - 3)))


def _request_json(
    provider: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int = 12,
) -> tuple[Any, str]:
    if _SESSION is None:
        return None, "requests_unavailable"
    if not _circuit_allows(provider):
        return None, "circuit_open"
    last_reason = "request_failed"
    for attempt in range(_MAX_RETRIES):
        try:
            response = _SESSION.get(url, params=params or {}, timeout=timeout)
            status = int(response.status_code)
            if status == 200:
                try:
                    payload = response.json()
                except ValueError:
                    _circuit_failure(provider, "invalid_json")
                    return None, "invalid_json"
                if isinstance(payload, dict):
                    error_text = str(
                        payload.get("error")
                        or payload.get("message")
                        or payload.get("Note")
                        or payload.get("Information")
                        or ""
                    )
                    if error_text and not any(
                        key in payload
                        for key in (
                            "values",
                            "historical",
                            "Global Quote",
                            "Time Series (Daily)",
                            "Weekly Time Series",
                            "Monthly Time Series",
                            "quarterlyReports",
                            "annualReports",
                        )
                    ):
                        last_reason = "provider_error"
                        if "limit" in error_text.lower() or "frequency" in error_text.lower():
                            last_reason = "rate_limit"
                        _circuit_failure(provider, last_reason)
                        return payload, last_reason
                _circuit_success(provider)
                return payload, ""
            if status == 429:
                last_reason = "rate_limit"
            elif status in {500, 502, 503, 504}:
                last_reason = f"http_{status}"
            else:
                _circuit_failure(provider, f"http_{status}")
                return None, f"http_{status}"
        except Exception as exc:
            last_reason = type(exc).__name__.lower()
        if attempt < _MAX_RETRIES - 1:
            time.sleep(min(5.0, 0.65 * (2**attempt)))
    _circuit_failure(provider, last_reason)
    return None, last_reason


def _base_symbol(symbol: str) -> str:
    value = str(symbol or "").strip().upper()
    value = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", value)
    if value.startswith("TADAWUL:"):
        value = value.split(":", 1)[1]
    return value


def _saudi_code(symbol: str) -> str | None:
    value = _base_symbol(symbol)
    value = value.replace(".SR", "").replace("^", "")
    return value if value.isdigit() else None


def _frame_from_records(records: Any) -> pd.DataFrame:
    if isinstance(records, dict):
        for key in ("historical", "values", "data"):
            if isinstance(records.get(key), list):
                records = records[key]
                break
    if not isinstance(records, list) or not records:
        return pd.DataFrame()
    frame = pd.DataFrame(records)
    if frame.empty:
        return pd.DataFrame()
    lower = {str(column).strip().lower(): column for column in frame.columns}
    date_column = next(
        (lower[key] for key in ("date", "datetime", "timestamp") if key in lower),
        None,
    )
    if date_column is None:
        return pd.DataFrame()
    if str(date_column).lower() == "timestamp" and pd.api.types.is_numeric_dtype(frame[date_column]):
        frame[date_column] = pd.to_datetime(frame[date_column], unit="s", utc=True, errors="coerce")
    else:
        frame[date_column] = pd.to_datetime(frame[date_column], utc=True, errors="coerce")
    rename: dict[Any, str] = {}
    aliases = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "adjusted_close": "Adj Close",
        "adjusted close": "Adj Close",
        "volume": "Volume",
    }
    for key, target in aliases.items():
        if key in lower:
            rename[lower[key]] = target
    frame = frame.rename(columns=rename)
    required = ["Open", "High", "Low", "Close"]
    if not all(column in frame.columns for column in required):
        return pd.DataFrame()
    for column in required + (["Volume"] if "Volume" in frame.columns else []):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "Volume" not in frame.columns:
        frame["Volume"] = 0.0
    frame = frame.dropna(subset=[date_column, *required]).set_index(date_column)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    return frame[["Open", "High", "Low", "Close", "Volume"]]


def _resample(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    output = pd.DataFrame(
        {
            "Open": frame["Open"].resample(rule).first(),
            "High": frame["High"].resample(rule).max(),
            "Low": frame["Low"].resample(rule).min(),
            "Close": frame["Close"].resample(rule).last(),
            "Volume": frame["Volume"].fillna(0).resample(rule).sum(),
        }
    ).dropna(subset=["Open", "High", "Low", "Close"])
    return output


def normalize_interval(interval: str) -> str:
    raw = str(interval or "1d").strip().lower()
    return {
        "60m": "1h",
        "60min": "1h",
        "1w": "1wk",
        "week": "1wk",
        "1week": "1wk",
        "month": "1mo",
        "1month": "1mo",
        "240m": "4h",
    }.get(raw, raw)


def validate_ohlcv(frame: pd.DataFrame, *, minimum_rows: int = _MIN_ROWS) -> dict[str, Any]:
    issues: list[str] = []
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return {"ok": False, "score": 0, "issues": ["empty"], "rows": 0}
    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = sorted(required - set(frame.columns))
    if missing:
        issues.append("missing:" + ",".join(missing))
    if not isinstance(frame.index, pd.DatetimeIndex):
        issues.append("non_datetime_index")
    if frame.index.has_duplicates:
        issues.append("duplicate_timestamps")
    if len(frame) < minimum_rows:
        issues.append("insufficient_rows")
    if required.issubset(frame.columns):
        open_ = pd.to_numeric(frame["Open"], errors="coerce")
        high = pd.to_numeric(frame["High"], errors="coerce")
        low = pd.to_numeric(frame["Low"], errors="coerce")
        close = pd.to_numeric(frame["Close"], errors="coerce")
        volume = pd.to_numeric(frame["Volume"], errors="coerce")
        invalid_prices = int(((open_ <= 0) | (high <= 0) | (low <= 0) | (close <= 0)).sum())
        invalid_geometry = int(((high < open_.combine(close, max)) | (low > open_.combine(close, min))).sum())
        negative_volume = int((volume < 0).sum())
        if invalid_prices:
            issues.append(f"invalid_prices:{invalid_prices}")
        if invalid_geometry:
            issues.append(f"invalid_geometry:{invalid_geometry}")
        if negative_volume:
            issues.append(f"negative_volume:{negative_volume}")
    score = max(0, 100 - 18 * len(issues))
    critical = any(
        item.startswith(("missing", "invalid_prices", "invalid_geometry"))
        or item in {"non_datetime_index", "empty"}
        for item in issues
    )
    return {"ok": not critical and len(frame) >= minimum_rows, "score": score, "issues": issues, "rows": len(frame)}


def _date_from_years(years: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=max(1, int(years)) * 366)).date().isoformat()


@lru_cache(maxsize=1024)
def _resolve_fmp_cached(symbol: str, bucket: int) -> str:
    _ = bucket
    key = _secret("FMP_API_KEY")
    if not key:
        return ""
    query = _saudi_code(symbol) or _base_symbol(symbol)
    payload, _reason = _request_json(
        "fmp",
        "https://financialmodelingprep.com/stable/search-symbol",
        params={"query": query, "apikey": key},
    )
    rows = payload if isinstance(payload, list) else []
    if not rows:
        return _base_symbol(symbol)

    def score(row: dict[str, Any]) -> int:
        candidate = str(row.get("symbol") or "").upper()
        exchange = " ".join(
            str(row.get(name) or "").upper()
            for name in ("exchange", "exchangeShortName", "exchangeFullName", "country")
        )
        result = 0
        if candidate.replace(".SR", "") == query.replace(".SR", ""):
            result += 50
        if any(word in exchange for word in ("SAUDI", "TADAWUL", "XSAU", "SAU")):
            result += 40
        return result

    best = max((row for row in rows if isinstance(row, dict)), key=score, default={})
    return str(best.get("symbol") or _base_symbol(symbol)).strip()


def resolve_fmp_symbol(symbol: str) -> str:
    return _resolve_fmp_cached(str(symbol), int(time.time() // 86_400))


@lru_cache(maxsize=1024)
def _resolve_eodhd_cached(symbol: str, bucket: int) -> str:
    _ = bucket
    key = _secret("EODHD_API_KEY")
    if not key:
        return ""
    query = _saudi_code(symbol) or _base_symbol(symbol).replace(".SR", "")
    payload, _reason = _request_json(
        "eodhd",
        f"https://eodhd.com/api/search/{query}",
        params={"api_token": key, "fmt": "json"},
    )
    rows = payload if isinstance(payload, list) else []
    if not rows:
        return ""

    def score(row: dict[str, Any]) -> int:
        code = str(row.get("Code") or row.get("code") or "").upper()
        context = " ".join(str(value or "").upper() for value in row.values())
        result = 0
        if code == query.upper():
            result += 50
        if any(word in context for word in ("SAUDI", "TADAWUL", "XSAU")):
            result += 50
        return result

    best = max((row for row in rows if isinstance(row, dict)), key=score, default={})
    code = str(best.get("Code") or best.get("code") or "").strip()
    exchange = str(best.get("Exchange") or best.get("exchange") or "").strip()
    return f"{code}.{exchange}" if code and exchange else ""


def resolve_eodhd_symbol(symbol: str) -> str:
    return _resolve_eodhd_cached(str(symbol), int(time.time() // 86_400))


@lru_cache(maxsize=1024)
def _resolve_alpha_cached(symbol: str, bucket: int) -> str:
    _ = bucket
    key = _secret("ALPHAVANTAGE_API_KEY")
    if not key:
        return ""
    query = _saudi_code(symbol) or _base_symbol(symbol)
    payload, _reason = _request_json(
        "alphavantage",
        "https://www.alphavantage.co/query",
        params={"function": "SYMBOL_SEARCH", "keywords": query, "apikey": key},
    )
    rows = payload.get("bestMatches") if isinstance(payload, dict) else []
    if not isinstance(rows, list) or not rows:
        return ""

    def score(row: dict[str, Any]) -> int:
        candidate = str(row.get("1. symbol") or "").upper()
        region = str(row.get("4. region") or "").upper()
        result = 0
        if candidate.split(".")[0] == query.split(".")[0]:
            result += 50
        if "SAUDI" in region:
            result += 50
        return result

    best = max((row for row in rows if isinstance(row, dict)), key=score, default={})
    return str(best.get("1. symbol") or "").strip()


def resolve_alpha_symbol(symbol: str) -> str:
    return _resolve_alpha_cached(str(symbol), int(time.time() // 86_400))


def _fetch_twelvedata_history(symbol: str, interval: str, years: int) -> tuple[pd.DataFrame, str]:
    try:
        from twelvedata_provider import get_time_series

        frame = get_time_series(symbol, interval=interval, years=years, outputsize=5000)
        return (frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()), str(symbol)
    except Exception:
        LOGGER.debug("Twelve Data history failed", exc_info=True)
        return pd.DataFrame(), str(symbol)


def _fetch_fmp_history(symbol: str, interval: str, years: int) -> tuple[pd.DataFrame, str]:
    key = _secret("FMP_API_KEY")
    resolved = resolve_fmp_symbol(symbol)
    if not key or not resolved:
        return pd.DataFrame(), resolved
    normalized = normalize_interval(interval)
    endpoint_interval = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1hour",
    }.get(normalized)
    if normalized == "4h":
        endpoint_interval = "1hour"
    if endpoint_interval:
        url = f"https://financialmodelingprep.com/stable/historical-chart/{endpoint_interval}"
    else:
        url = "https://financialmodelingprep.com/stable/historical-price-eod/full"
    payload, _reason = _request_json(
        "fmp",
        url,
        params={
            "symbol": resolved,
            "from": _date_from_years(years),
            "apikey": key,
        },
    )
    frame = _frame_from_records(payload)
    if normalized == "4h" and not frame.empty:
        frame = _resample(frame, "4h")
    elif normalized == "1wk" and not frame.empty:
        frame = _resample(frame, "W-THU")
    elif normalized == "1mo" and not frame.empty:
        frame = _resample(frame, "ME")
    return frame, resolved


def _fetch_eodhd_history(symbol: str, interval: str, years: int) -> tuple[pd.DataFrame, str]:
    key = _secret("EODHD_API_KEY")
    resolved = resolve_eodhd_symbol(symbol)
    if not key or not resolved:
        return pd.DataFrame(), resolved
    normalized = normalize_interval(interval)
    intraday_base = {
        "1m": "1m",
        "5m": "5m",
        "15m": "5m",
        "30m": "5m",
        "1h": "1h",
        "4h": "1h",
    }.get(normalized)
    if intraday_base:
        now = int(time.time())
        start = int((datetime.now(timezone.utc) - timedelta(days=min(720, max(14, years * 365)))).timestamp())
        payload, _reason = _request_json(
            "eodhd",
            f"https://eodhd.com/api/intraday/{resolved}",
            params={
                "api_token": key,
                "fmt": "json",
                "interval": intraday_base,
                "from": start,
                "to": now,
            },
        )
        frame = _frame_from_records(payload)
        if normalized == "15m" and not frame.empty:
            frame = _resample(frame, "15min")
        elif normalized == "30m" and not frame.empty:
            frame = _resample(frame, "30min")
        elif normalized == "4h" and not frame.empty:
            frame = _resample(frame, "4h")
        return frame, resolved
    payload, _reason = _request_json(
        "eodhd",
        f"https://eodhd.com/api/eod/{resolved}",
        params={
            "api_token": key,
            "fmt": "json",
            "period": "d",
            "order": "a",
            "from": _date_from_years(years),
        },
    )
    frame = _frame_from_records(payload)
    if normalized == "1wk" and not frame.empty:
        frame = _resample(frame, "W-THU")
    elif normalized == "1mo" and not frame.empty:
        frame = _resample(frame, "ME")
    return frame, resolved


def _alpha_series_key(payload: dict[str, Any]) -> str | None:
    return next(
        (
            key
            for key, value in payload.items()
            if isinstance(value, dict) and ("Time Series" in key or "Weekly" in key or "Monthly" in key)
        ),
        None,
    )


def _fetch_alpha_history(symbol: str, interval: str, years: int) -> tuple[pd.DataFrame, str]:
    key = _secret("ALPHAVANTAGE_API_KEY")
    resolved = resolve_alpha_symbol(symbol)
    if not key or not resolved:
        return pd.DataFrame(), resolved
    normalized = normalize_interval(interval)
    params: dict[str, Any] = {"symbol": resolved, "apikey": key, "datatype": "json"}
    if normalized in {"1m", "5m", "15m", "30m", "1h", "4h"}:
        params["function"] = "TIME_SERIES_INTRADAY"
        params["interval"] = "60min" if normalized in {"1h", "4h"} else normalized
        params["outputsize"] = "full"
    elif normalized == "1wk":
        params["function"] = "TIME_SERIES_WEEKLY"
    elif normalized == "1mo":
        params["function"] = "TIME_SERIES_MONTHLY"
    else:
        params["function"] = "TIME_SERIES_DAILY"
        params["outputsize"] = "full"
    payload, _reason = _request_json(
        "alphavantage", "https://www.alphavantage.co/query", params=params
    )
    if not isinstance(payload, dict):
        return pd.DataFrame(), resolved
    series_key = _alpha_series_key(payload)
    if not series_key:
        return pd.DataFrame(), resolved
    records = []
    for timestamp, row in payload[series_key].items():
        if not isinstance(row, dict):
            continue
        records.append(
            {
                "date": timestamp,
                "open": row.get("1. open"),
                "high": row.get("2. high"),
                "low": row.get("3. low"),
                "close": row.get("4. close"),
                "volume": row.get("5. volume", 0),
            }
        )
    frame = _frame_from_records(records)
    if normalized == "4h" and not frame.empty:
        frame = _resample(frame, "4h")
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, years) * 366)
    if not frame.empty:
        frame = frame[frame.index >= cutoff]
    return frame, resolved


_HISTORY_ADAPTERS: dict[str, Callable[[str, str, int], tuple[pd.DataFrame, str]]] = {
    "twelvedata": _fetch_twelvedata_history,
    "fmp": _fetch_fmp_history,
    "eodhd": _fetch_eodhd_history,
    "alphavantage": _fetch_alpha_history,
}


def fetch_history(
    symbol: str,
    *,
    interval: str = "1d",
    years: int = 5,
    minimum_rows: int = _MIN_ROWS,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    attempts: list[ProviderAttempt] = []
    for provider in configured_provider_order():
        if not _secret(_SECRET_NAMES[provider]):
            attempts.append(ProviderAttempt(provider, False, "not_configured"))
            continue
        started = time.perf_counter()
        try:
            frame, resolved = _HISTORY_ADAPTERS[provider](symbol, interval, years)
        except Exception as exc:  # fail closed; never expose provider internals to UI
            LOGGER.exception("%s history adapter failed", provider)
            frame, resolved = pd.DataFrame(), ""
            reason = type(exc).__name__.lower()
        else:
            reason = ""
        elapsed = int((time.perf_counter() - started) * 1000)
        quality = validate_ohlcv(frame, minimum_rows=minimum_rows)
        ok = bool(quality["ok"])
        attempts.append(
            ProviderAttempt(
                provider,
                ok,
                reason or ("" if ok else ";".join(quality["issues"])),
                rows=int(quality["rows"]),
                resolved_symbol=resolved,
                elapsed_ms=elapsed,
                quality_score=int(quality["score"]),
            )
        )
        if not ok:
            continue
        frame = frame.copy()
        fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        lineage = {
            "source": provider,
            "symbol": str(symbol),
            "resolved_symbol": resolved,
            "interval": normalize_interval(interval),
            "rows": int(len(frame)),
            "start": str(frame.index.min()),
            "end": str(frame.index.max()),
            "fetched_at": fetched_at,
            "quality_score": int(quality["score"]),
            "provider_attempts": [item.as_dict() for item in attempts],
            "provider_order": configured_provider_order(),
            "is_stale": False,
            "fusion_version": "5.0",
        }
        frame.attrs["source"] = provider
        frame.attrs["data_lineage"] = lineage
        return frame, [item.as_dict() for item in attempts]
    return pd.DataFrame(), [item.as_dict() for item in attempts]


def _quote_twelvedata(symbol: str) -> tuple[dict[str, Any], str]:
    try:
        from twelvedata_provider import get_quote

        payload = get_quote(symbol)
        if isinstance(payload, dict) and payload.get("ok"):
            return {
                "price": payload.get("price"),
                "prev_close": payload.get("prev_close"),
                "year_high": payload.get("fifty_two_week_high"),
                "year_low": payload.get("fifty_two_week_low"),
            }, str(symbol)
    except Exception:
        LOGGER.debug("Twelve Data quote failed", exc_info=True)
    return {}, str(symbol)


def _quote_fmp(symbol: str) -> tuple[dict[str, Any], str]:
    key = _secret("FMP_API_KEY")
    resolved = resolve_fmp_symbol(symbol)
    if not key or not resolved:
        return {}, resolved
    payload, _reason = _request_json(
        "fmp",
        "https://financialmodelingprep.com/stable/quote",
        params={"symbol": resolved, "apikey": key},
    )
    row = payload[0] if isinstance(payload, list) and payload else payload if isinstance(payload, dict) else {}
    return {
        "price": row.get("price"),
        "prev_close": row.get("previousClose"),
        "year_high": row.get("yearHigh"),
        "year_low": row.get("yearLow"),
        "volume": row.get("volume"),
    }, resolved


def _quote_eodhd(symbol: str) -> tuple[dict[str, Any], str]:
    key = _secret("EODHD_API_KEY")
    resolved = resolve_eodhd_symbol(symbol)
    if not key or not resolved:
        return {}, resolved
    payload, _reason = _request_json(
        "eodhd",
        f"https://eodhd.com/api/real-time/{resolved}",
        params={"api_token": key, "fmt": "json"},
    )
    row = payload if isinstance(payload, dict) else {}
    return {
        "price": row.get("close"),
        "prev_close": row.get("previousClose"),
        "year_high": None,
        "year_low": None,
        "volume": row.get("volume"),
    }, resolved


def _quote_alpha(symbol: str) -> tuple[dict[str, Any], str]:
    key = _secret("ALPHAVANTAGE_API_KEY")
    resolved = resolve_alpha_symbol(symbol)
    if not key or not resolved:
        return {}, resolved
    payload, _reason = _request_json(
        "alphavantage",
        "https://www.alphavantage.co/query",
        params={"function": "GLOBAL_QUOTE", "symbol": resolved, "apikey": key},
    )
    row = payload.get("Global Quote") if isinstance(payload, dict) else {}
    row = row if isinstance(row, dict) else {}
    return {
        "price": row.get("05. price"),
        "prev_close": row.get("08. previous close"),
        "year_high": None,
        "year_low": None,
        "volume": row.get("06. volume"),
    }, resolved


_QUOTE_ADAPTERS: dict[str, Callable[[str], tuple[dict[str, Any], str]]] = {
    "twelvedata": _quote_twelvedata,
    "fmp": _quote_fmp,
    "eodhd": _quote_eodhd,
    "alphavantage": _quote_alpha,
}


def _finite_positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def fetch_quote(symbol: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    for provider in configured_provider_order():
        if not _secret(_SECRET_NAMES[provider]):
            attempts.append({"provider": provider, "ok": False, "reason": "not_configured"})
            continue
        started = time.perf_counter()
        try:
            raw, resolved = _QUOTE_ADAPTERS[provider](symbol)
        except Exception:
            LOGGER.exception("%s quote adapter failed", provider)
            raw, resolved = {}, ""
        price = _finite_positive(raw.get("price"))
        previous = _finite_positive(raw.get("prev_close"))
        elapsed = int((time.perf_counter() - started) * 1000)
        ok = price is not None
        attempts.append(
            {
                "provider": provider,
                "ok": ok,
                "reason": "" if ok else "invalid_or_missing_price",
                "resolved_symbol": resolved,
                "elapsed_ms": elapsed,
            }
        )
        if not ok:
            continue
        change = ((price - previous) / previous) * 100.0 if previous else None
        return {
            "symbol": str(symbol),
            "resolved_symbol": resolved,
            "price": price,
            "prev_close": previous,
            "previous_close": previous,
            "change_pct": round(change, 4) if change is not None else None,
            "change_percent": round(change, 4) if change is not None else None,
            "change_available": change is not None,
            "year_high": _finite_positive(raw.get("year_high")),
            "year_low": _finite_positive(raw.get("year_low")),
            "volume": _finite_positive(raw.get("volume")),
            "source": provider,
            "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "is_stale": False,
            "provider_attempts": attempts,
            "fusion_version": "5.0",
        }, attempts
    return {}, attempts


__all__ = [
    "configured_provider_order",
    "fetch_history",
    "fetch_quote",
    "normalize_interval",
    "provider_status",
    "resolve_alpha_symbol",
    "resolve_eodhd_symbol",
    "resolve_fmp_symbol",
    "validate_ohlcv",
]
