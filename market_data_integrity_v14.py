"""Production integrity layer for Osoli market and financial data.

This layer closes four source-level gaps without changing public APIs:
- one HTTP attempt must not outlive the total provider deadline;
- intraday timestamps are normalized to UTC instead of treating exchange-local
  text as UTC;
- quote refreshes run per symbol with bounded parallelism and no hidden queue;
- operating cash flow aliases never accept investing cash flow.
"""
from __future__ import annotations

import copy
import logging
import math
import threading
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Callable

import pandas as pd

LOGGER = logging.getLogger(__name__)
_INSTALL_LOCK = threading.RLock()
_INSTALLED = False
_FRAME_TIMEZONE_HINT: ContextVar[str | None] = ContextVar(
    "osoli_frame_timezone_hint_v14",
    default=None,
)


def _response_error(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    error_text = str(
        payload.get("error")
        or payload.get("message")
        or payload.get("Note")
        or payload.get("Information")
        or ""
    )
    if not error_text:
        return ""
    accepted = {
        "values",
        "historical",
        "Global Quote",
        "Time Series (Daily)",
        "Weekly Time Series",
        "Monthly Time Series",
        "quarterlyReports",
        "annualReports",
    }
    if any(key in payload for key in accepted):
        return ""
    lowered = error_text.lower()
    return "rate_limit" if "limit" in lowered or "frequency" in lowered else "provider_error"


def _strict_request_json(
    provider: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = 12,
) -> tuple[Any, str]:
    """Execute exactly one bounded HTTP request.

    The V8 wrapper previously calculated the remaining budget once and then
    called the legacy helper, which could retry three times with that same
    timeout. A single adapter could therefore exceed the advertised total
    deadline. This implementation owns the request and never retries inside the
    interactive or background worker.
    """
    import market_providers_v5 as providers
    import sc_runtime_v8 as runtime

    session = providers._SESSION  # noqa: SLF001
    if session is None:
        return None, "requests_unavailable"
    if not providers._circuit_allows(provider):  # noqa: SLF001
        return None, "circuit_open"

    remaining = runtime._remaining(max(0.2, float(timeout or 1.0)))  # noqa: SLF001
    budget = min(max(0.0, float(timeout or 1.0)), remaining)
    if budget < 0.15:
        return None, "total_deadline_exceeded"
    connect = min(0.8, max(0.20, budget * 0.25))
    read = max(0.20, budget - connect)
    started = time.monotonic()
    try:
        response = session.get(
            url,
            params=params or {},
            timeout=(round(connect, 3), round(read, 3)),
        )
        status = int(response.status_code)
        if status != 200:
            reason = (
                "rate_limit"
                if status == 429
                else f"http_{status}"
            )
            providers._circuit_failure(provider, reason)  # noqa: SLF001
            return None, reason
        try:
            payload = response.json()
        except ValueError:
            providers._circuit_failure(provider, "invalid_json")  # noqa: SLF001
            return None, "invalid_json"
        reason = _response_error(payload)
        if reason:
            providers._circuit_failure(provider, reason)  # noqa: SLF001
            return payload, reason
        providers._circuit_success(provider)  # noqa: SLF001
        return payload, ""
    except Exception as exc:
        reason = type(exc).__name__.lower()
        if time.monotonic() - started >= budget - 0.05:
            reason = "request_timeout"
        providers._circuit_failure(provider, reason)  # noqa: SLF001
        return None, reason


def _extract_records(records: Any) -> list[dict[str, Any]]:
    if isinstance(records, dict):
        for key in ("historical", "values", "data"):
            value = records.get(key)
            if isinstance(value, list):
                records = value
                break
    return [item for item in records if isinstance(item, dict)] if isinstance(records, list) else []


def _parse_datetime(values: pd.Series, *, numeric_epoch: bool, timezone_hint: str | None) -> pd.Series:
    if numeric_epoch:
        numeric = pd.to_numeric(values, errors="coerce")
        # Providers may return milliseconds; normalize them before conversion.
        median = numeric.dropna().median() if not numeric.dropna().empty else 0
        unit = "ms" if float(median or 0) > 10_000_000_000 else "s"
        return pd.to_datetime(numeric, unit=unit, utc=True, errors="coerce")

    parsed = pd.to_datetime(values, errors="coerce")
    try:
        current_tz = parsed.dt.tz
    except (AttributeError, TypeError):
        return pd.to_datetime(values, utc=True, errors="coerce")
    if current_tz is not None:
        return parsed.dt.tz_convert("UTC")
    hint = timezone_hint or _FRAME_TIMEZONE_HINT.get()
    if hint:
        try:
            return parsed.dt.tz_localize(
                hint,
                ambiguous="infer",
                nonexistent="shift_forward",
            ).dt.tz_convert("UTC")
        except Exception:
            LOGGER.info("Unable to localize provider timestamps with %s", hint, exc_info=True)
    return parsed.dt.tz_localize("UTC")


def _frame_from_records_utc(
    records: Any,
    *,
    timezone_hint: str | None = None,
) -> pd.DataFrame:
    """Normalize OHLCV records and prefer an unambiguous Unix timestamp."""
    rows = _extract_records(records)
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame()
    lower = {str(column).strip().lower(): column for column in frame.columns}

    timestamp_column = lower.get("timestamp")
    numeric_timestamp = bool(
        timestamp_column is not None
        and pd.api.types.is_numeric_dtype(frame[timestamp_column])
    )
    date_column = (
        timestamp_column
        if numeric_timestamp
        else next(
            (lower[key] for key in ("date", "datetime", "timestamp") if key in lower),
            None,
        )
    )
    if date_column is None:
        return pd.DataFrame()
    frame[date_column] = _parse_datetime(
        frame[date_column],
        numeric_epoch=numeric_timestamp,
        timezone_hint=timezone_hint,
    )

    aliases = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "adjusted_close": "Adj Close",
        "adjusted close": "Adj Close",
        "volume": "Volume",
    }
    rename = {
        lower[key]: target
        for key, target in aliases.items()
        if key in lower
    }
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


def _timezone_for_symbol(symbol: str, interval: str) -> str | None:
    import market_providers_v5 as providers

    normalized = providers.normalize_interval(interval)
    if normalized not in {"1m", "5m", "15m", "30m", "1h", "4h"}:
        return None
    if providers._saudi_code(symbol):  # noqa: SLF001
        return "Asia/Riyadh"
    value = providers._base_symbol(symbol)  # noqa: SLF001
    if "/" in value or "=" in value or value.endswith(("USD", "USDT")):
        return "UTC"
    return "America/New_York"


def _wrap_history_timezone(
    adapter: Callable[[str, str, int], tuple[pd.DataFrame, str]],
) -> Callable[[str, str, int], tuple[pd.DataFrame, str]]:
    def wrapped(symbol: str, interval: str, years: int) -> tuple[pd.DataFrame, str]:
        token = _FRAME_TIMEZONE_HINT.set(_timezone_for_symbol(symbol, interval))
        try:
            return adapter(symbol, interval, years)
        finally:
            _FRAME_TIMEZONE_HINT.reset(token)

    return wrapped


def _install_timestamp_integrity() -> None:
    import bounded_twelvedata_v9 as bounded
    import market_providers_v5 as providers

    providers._frame_from_records = _frame_from_records_utc  # noqa: SLF001
    for name in ("fmp", "eodhd", "alphavantage"):
        current = providers._HISTORY_ADAPTERS[name]  # noqa: SLF001
        if not getattr(current, "_osoli_timezone_v14", False):
            wrapped = _wrap_history_timezone(current)
            wrapped._osoli_timezone_v14 = True  # type: ignore[attr-defined]
            providers._HISTORY_ADAPTERS[name] = wrapped  # noqa: SLF001

    original_td_request = bounded._request_json  # noqa: SLF001
    if not getattr(original_td_request, "_osoli_timezone_v14", False):

        def td_request(
            endpoint: str,
            *,
            params: dict[str, Any],
            budget: float,
        ) -> Any:
            clean = dict(params)
            interval = str(clean.get("interval") or "").lower()
            if endpoint == "time_series" and interval not in {
                "1day",
                "1week",
                "1month",
            }:
                clean["timezone"] = "UTC"
            return original_td_request(endpoint, params=clean, budget=budget)

        td_request._osoli_timezone_v14 = True  # type: ignore[attr-defined]
        bounded._request_json = td_request  # noqa: SLF001


def _quote_payload(value: Any, symbol: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    candidates = (
        symbol,
        symbol.upper(),
        symbol.replace(".SR", ""),
        f"{symbol.replace('.SR', '')}.SR",
    )
    for key in candidates:
        payload = value.get(key)
        if isinstance(payload, dict):
            return payload
    return {}


def _install_parallel_quote_refresh() -> None:
    import market_data
    import performance_runtime_v7 as runtime

    current = market_data.fetch_batch_data
    if getattr(current, "_osoli_per_symbol_v14", False):
        return
    provider_batch = getattr(current, "_osoli_original", current)

    def fetch_batch_data(symbols_list: list) -> dict[str, dict[str, Any]]:
        requested = list(
            dict.fromkeys(
                runtime._normalized_symbol(value)  # noqa: SLF001
                for value in symbols_list or []
                if runtime._normalized_symbol(value)  # noqa: SLF001
            )
        )
        output: dict[str, dict[str, Any]] = {}
        missing: list[str] = []
        stale: list[str] = []
        for symbol in requested:
            cached = runtime.peek_cached_quote(symbol, allow_stale=True)
            if cached:
                output[symbol] = cached
                if cached.get("is_stale"):
                    stale.append(symbol)
            else:
                missing.append(symbol)

        refresh_order = [*missing, *(item for item in stale if item not in missing)]
        futures: dict[str, Any] = {}
        for symbol in refresh_order:

            def loader(symbol: str = symbol) -> dict[str, dict[str, Any]]:
                started = time.perf_counter()
                result = provider_batch([symbol]) or {}
                runtime.record_phase(
                    symbol,
                    "quote",
                    "header_quote_ms",
                    (time.perf_counter() - started) * 1000.0,
                )
                return result if isinstance(result, dict) else {}

            def saver(value: Any, symbol: str = symbol) -> None:
                payload = _quote_payload(value, symbol)
                if payload:
                    runtime._store_quote(symbol, payload)  # noqa: SLF001

            future = runtime._submit_once("quotes", symbol, loader, saver)  # noqa: SLF001
            if future is not None:
                futures[symbol] = future

        if not missing:
            return output

        deadline = time.monotonic() + runtime._QUOTE_BUDGET  # noqa: SLF001
        for symbol in missing:
            future = futures.get(symbol)
            remaining = deadline - time.monotonic()
            if future is None or remaining <= 0.05:
                continue
            loaded = runtime._wait(future, remaining)  # noqa: SLF001
            if isinstance(loaded, dict):
                payload = _quote_payload(loaded, symbol)
                if payload:
                    runtime._store_quote(symbol, payload)  # noqa: SLF001

        for symbol in requested:
            payload = runtime.peek_cached_quote(symbol, allow_stale=True)
            if payload:
                output[symbol] = payload
        return output

    fetch_batch_data.__name__ = "fetch_batch_data"
    fetch_batch_data._osoli_original = provider_batch  # type: ignore[attr-defined]
    fetch_batch_data._osoli_per_symbol_v14 = True  # type: ignore[attr-defined]
    market_data.fetch_batch_data = fetch_batch_data


def _install_financial_alias_integrity() -> None:
    import financial_providers_v5 as financial

    aliases = tuple(
        item
        for item in financial._CANONICAL_ALIASES["operating_cash_flow"]  # noqa: SLF001
        if str(item).casefold() != "cashflowfrominvestment"
    )
    additions = (
        "netCashProvidedByOperatingActivities",
        "cashFlowsFromUsedInOperatingActivities",
    )
    financial._CANONICAL_ALIASES["operating_cash_flow"] = tuple(  # noqa: SLF001
        dict.fromkeys((*aliases, *additions))
    )


def runtime_status() -> dict[str, Any]:
    import bounded_twelvedata_v9 as bounded
    import financial_providers_v5 as financial
    import market_data
    import market_providers_v5 as providers

    return {
        "installed": _INSTALLED,
        "strict_single_http_attempt": providers._request_json is _strict_request_json,  # noqa: SLF001
        "utc_timestamp_normalization": providers._frame_from_records is _frame_from_records_utc,  # noqa: SLF001
        "twelvedata_intraday_utc": bool(
            getattr(bounded._request_json, "_osoli_timezone_v14", False)  # noqa: SLF001
        ),
        "per_symbol_quote_refresh": bool(
            getattr(market_data.fetch_batch_data, "_osoli_per_symbol_v14", False)
        ),
        "operating_cash_flow_aliases": list(
            financial._CANONICAL_ALIASES["operating_cash_flow"]  # noqa: SLF001
        ),
    }


def install_market_data_integrity_v14() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        import market_providers_v5 as providers

        providers._request_json = _strict_request_json  # noqa: SLF001
        _install_timestamp_integrity()
        _install_parallel_quote_refresh()
        _install_financial_alias_integrity()
        _INSTALLED = True


__all__ = [
    "_frame_from_records_utc",
    "_strict_request_json",
    "install_market_data_integrity_v14",
    "runtime_status",
]
