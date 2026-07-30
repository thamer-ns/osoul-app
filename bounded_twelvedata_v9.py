"""Strict single-request Twelve Data adapters for Osoli V9.

The legacy Twelve Data helper intentionally retries several SDK and HTTP paths.
That behavior is useful for batch jobs, but it can keep an interactive Streamlit
request blocked long after the V8 provider deadline has expired.  This module
installs direct HTTP adapters with one bounded request per history/quote attempt.
The normal process and persistent caches still remain in front of these adapters.
"""
from __future__ import annotations

import logging
import math
import os
import threading
from typing import Any

import pandas as pd

import market_providers_v5 as providers

LOGGER = logging.getLogger(__name__)
_INSTALL_LOCK = threading.RLock()
_INSTALLED = False
_HISTORY_BUDGET = max(
    1.0,
    min(
        4.0,
        float(os.getenv("OSOUL_TWELVEDATA_HISTORY_DEADLINE_SECONDS", "3.2")),
    ),
)
_QUOTE_BUDGET = max(
    0.5,
    min(
        2.0,
        float(os.getenv("OSOUL_TWELVEDATA_QUOTE_DEADLINE_SECONDS", "1.4")),
    ),
)
_SESSION = providers.requests.Session() if providers.requests is not None else None
if _SESSION is not None:
    _SESSION.headers.update(
        {
            "User-Agent": "Osoli/9.0 bounded-twelvedata",
            "Accept": "application/json,text/plain,*/*",
        }
    )


def _symbol_params(symbol: str) -> tuple[str, str, str]:
    value = str(symbol or "").strip().upper()
    value = value.replace("^", "")
    if value.startswith("TADAWUL:"):
        value = value.split(":", 1)[1]
    if value.endswith(".SR"):
        value = value[:-3]
    if value in {
        "TADAWUL",
        "TADAWUL ALL SHARE",
        "TADAWUL ALL SHARE INDEX",
    }:
        value = "TASI"
    exchange = "XSAU" if value.isdigit() or value == "TASI" else ""
    resolved = f"{value}:{exchange}" if exchange else value
    return value, exchange, resolved


def _interval(value: str) -> tuple[str, str | None]:
    normalized = providers.normalize_interval(value)
    mapped = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
        "4h": "1h",
        "1d": "1day",
        "1wk": "1week",
        "1mo": "1month",
    }.get(normalized, normalized)
    return mapped, "4h" if normalized == "4h" else None


def _outputsize(interval: str, years: int) -> int:
    normalized = providers.normalize_interval(interval)
    safe_years = max(1, int(years or 1))
    if normalized in {"1m", "5m", "15m", "30m", "1h", "4h"}:
        return 5000
    if normalized == "1wk":
        return max(120, min(5000, safe_years * 55 + 20))
    if normalized == "1mo":
        return max(120, min(5000, safe_years * 13 + 20))
    return max(200, min(5000, safe_years * 260 + 50))


def _timeouts(total_budget: float) -> tuple[float, float]:
    connect = min(0.8, max(0.25, total_budget * 0.25))
    read = max(0.25, total_budget - connect)
    return round(connect, 3), round(read, 3)


def _request_json(
    endpoint: str,
    *,
    params: dict[str, Any],
    budget: float,
) -> Any:
    if _SESSION is None:
        return None
    try:
        response = _SESSION.get(
            f"https://api.twelvedata.com/{endpoint}",
            params=params,
            timeout=_timeouts(budget),
        )
    except Exception:
        LOGGER.info("Bounded Twelve Data request failed", exc_info=True)
        return None
    if int(getattr(response, "status_code", 0) or 0) != 200:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if isinstance(payload, dict):
        status = str(payload.get("status") or "").strip().lower()
        if status == "error":
            return None
        if payload.get("code") and not payload.get("values"):
            return None
    return payload


def _history_adapter(
    symbol: str,
    interval: str,
    years: int,
) -> tuple[pd.DataFrame, str]:
    key = providers._secret("TWELVEDATA_API_KEY")  # noqa: SLF001
    api_symbol, exchange, resolved = _symbol_params(symbol)
    if not key or not api_symbol:
        return pd.DataFrame(), resolved
    api_interval, resample = _interval(interval)
    params: dict[str, Any] = {
        "symbol": api_symbol,
        "interval": api_interval,
        "outputsize": _outputsize(interval, years),
        "format": "JSON",
        "apikey": key,
    }
    if exchange:
        params["exchange"] = exchange
    payload = _request_json(
        "time_series",
        params=params,
        budget=_HISTORY_BUDGET,
    )
    values = payload.get("values") if isinstance(payload, dict) else payload
    frame = providers._frame_from_records(values)  # noqa: SLF001
    if resample and not frame.empty:
        frame = providers._resample(frame, resample)  # noqa: SLF001
    return frame, resolved


def _positive(value: Any) -> float | None:
    try:
        number = float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _quote_adapter(symbol: str) -> tuple[dict[str, Any], str]:
    key = providers._secret("TWELVEDATA_API_KEY")  # noqa: SLF001
    api_symbol, exchange, resolved = _symbol_params(symbol)
    if not key or not api_symbol:
        return {}, resolved
    params: dict[str, Any] = {
        "symbol": api_symbol,
        "apikey": key,
    }
    if exchange:
        params["exchange"] = exchange
    payload = _request_json("quote", params=params, budget=_QUOTE_BUDGET)
    row = payload if isinstance(payload, dict) else {}
    price = _positive(row.get("close") or row.get("price") or row.get("last"))
    if price is None:
        return {}, resolved
    return {
        "price": price,
        "prev_close": _positive(
            row.get("previous_close") or row.get("prev_close")
        ),
        "year_high": _positive(
            row.get("fifty_two_week", {}).get("high")
            if isinstance(row.get("fifty_two_week"), dict)
            else row.get("fifty_two_week_high")
        ),
        "year_low": _positive(
            row.get("fifty_two_week", {}).get("low")
            if isinstance(row.get("fifty_two_week"), dict)
            else row.get("fifty_two_week_low")
        ),
        "volume": _positive(row.get("volume")),
    }, resolved


def runtime_status() -> dict[str, Any]:
    return {
        "installed": _INSTALLED,
        "history_deadline_seconds": _HISTORY_BUDGET,
        "quote_deadline_seconds": _QUOTE_BUDGET,
        "single_request": True,
        "sdk_retries_disabled": True,
    }


def install_bounded_twelvedata_v9() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        providers._HISTORY_ADAPTERS["twelvedata"] = _history_adapter  # noqa: SLF001
        providers._QUOTE_ADAPTERS["twelvedata"] = _quote_adapter  # noqa: SLF001
        _INSTALLED = True


__all__ = ["install_bounded_twelvedata_v9", "runtime_status"]
