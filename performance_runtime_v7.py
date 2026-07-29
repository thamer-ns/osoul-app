"""Bounded, stale-while-revalidate data access for interactive Osoli pages."""
from __future__ import annotations

import copy
import logging
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Callable, Hashable

import pandas as pd

LOGGER = logging.getLogger(__name__)
_INSTALL_LOCK = threading.RLock()
_CACHE_LOCK = threading.RLock()
_INSTALLED = False

_MAX_WORKERS = max(2, min(8, int(os.getenv("OSOUL_IO_WORKERS", "4"))))
_MAX_INFLIGHT = max(_MAX_WORKERS, int(os.getenv("OSOUL_IO_MAX_INFLIGHT", "10")))
_EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="osoli-io")
_INFLIGHT: dict[tuple[str, Hashable], Future[Any]] = {}
_HISTORY_CACHE: dict[Hashable, tuple[float, pd.DataFrame]] = {}
_QUOTE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_FINANCIAL_CACHE: dict[Hashable, tuple[float, pd.DataFrame, dict[str, Any]]] = {}
_TRACE: dict[tuple[str, str], dict[str, float]] = {}

_ACTIVE_HISTORY: ContextVar[tuple[str, str, pd.DataFrame] | None] = ContextVar(
    "osoli_active_history", default=None
)

_HISTORY_BUDGET = max(
    1.0, float(os.getenv("OSOUL_HISTORY_INTERACTIVE_BUDGET_SECONDS", "6"))
)
_QUOTE_BUDGET = max(
    0.5, float(os.getenv("OSOUL_QUOTE_INTERACTIVE_BUDGET_SECONDS", "3"))
)
_FINANCIAL_BUDGET = max(
    1.0, float(os.getenv("OSOUL_FINANCIAL_INTERACTIVE_BUDGET_SECONDS", "3"))
)
_PROVIDER_TIMEOUT = max(
    1.0, float(os.getenv("OSOUL_PROVIDER_REQUEST_TIMEOUT_SECONDS", "3"))
)


def _clone(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        output = value.copy(deep=True)
        output.attrs.update(copy.deepcopy(dict(getattr(value, "attrs", {}) or {})))
        return output
    return copy.deepcopy(value)


def _normalized_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalized_interval(value: Any) -> str:
    raw = str(value or "1d").strip().lower()
    return {
        "60m": "1h",
        "1w": "1wk",
        "week": "1wk",
        "weekly": "1wk",
        "month": "1mo",
        "monthly": "1mo",
    }.get(raw, raw)


def analysis_row_limit(interval: str) -> int:
    frame = _normalized_interval(interval)
    if frame in {"1m", "2m", "5m", "15m"}:
        return 1200
    if frame in {"30m", "1h", "4h"}:
        return 1600
    if frame == "1d":
        return 1800
    if frame == "1wk":
        return 1200
    if frame == "1mo":
        return 600
    return 1600


def _history_ttl(interval: str) -> float:
    frame = _normalized_interval(interval)
    if frame in {"1m", "2m", "5m", "15m", "30m", "1h", "4h"}:
        return max(
            30.0,
            float(os.getenv("OSOUL_HISTORY_INTRADAY_TTL_SECONDS", "120")),
        )
    if frame == "1d":
        return max(
            300.0,
            float(os.getenv("OSOUL_HISTORY_DAILY_TTL_SECONDS", "1200")),
        )
    return max(
        1800.0,
        float(os.getenv("OSOUL_HISTORY_HIGHER_TTL_SECONDS", "10800")),
    )


def _history_stale_ttl(interval: str) -> float:
    return max(_history_ttl(interval) * 12.0, 6 * 3600.0)


def _quote_ttl() -> float:
    return max(30.0, float(os.getenv("OSOUL_QUOTE_TTL_SECONDS", "90")))


def _financial_ttl() -> float:
    return max(
        3600.0,
        float(os.getenv("OSOUL_FINANCIAL_TTL_SECONDS", "21600")),
    )


def _trace_key(symbol: str, timeframe: str) -> tuple[str, str]:
    return (_normalized_symbol(symbol), _normalized_interval(timeframe))


def record_phase(symbol: str, timeframe: str, phase: str, elapsed_ms: float) -> None:
    with _CACHE_LOCK:
        _TRACE.setdefault(_trace_key(symbol, timeframe), {})[str(phase)] = round(
            max(0.0, float(elapsed_ms)), 3
        )


def performance_trace(symbol: str, timeframe: str) -> dict[str, float]:
    with _CACHE_LOCK:
        return dict(_TRACE.get(_trace_key(symbol, timeframe), {}))


def clear_performance_trace(symbol: str, timeframe: str) -> None:
    with _CACHE_LOCK:
        _TRACE.pop(_trace_key(symbol, timeframe), None)


def activate_history(symbol: str, interval: str, frame: pd.DataFrame):
    return _ACTIVE_HISTORY.set(
        (_normalized_symbol(symbol), _normalized_interval(interval), _clone(frame))
    )


def deactivate_history(token: Any) -> None:
    _ACTIVE_HISTORY.reset(token)


def _active_history(symbol: str, interval: str) -> pd.DataFrame | None:
    value = _ACTIVE_HISTORY.get()
    if value is None:
        return None
    active_symbol, active_interval, frame = value
    if (
        active_symbol == _normalized_symbol(symbol)
        and active_interval == _normalized_interval(interval)
    ):
        return _clone(frame)
    return None


def _mark_stale(frame: pd.DataFrame, stale: bool) -> pd.DataFrame:
    output = _clone(frame)
    attrs = dict(getattr(output, "attrs", {}) or {})
    lineage = dict(attrs.get("data_lineage") or {})
    lineage["is_stale"] = bool(stale)
    lineage["cache_mode"] = "stale_while_revalidate" if stale else "fresh"
    attrs["data_lineage"] = lineage
    output.attrs.update(attrs)
    return output


def _submit_once(
    namespace: str,
    key: Hashable,
    loader: Callable[[], Any],
    saver: Callable[[Any], None],
) -> Future[Any] | None:
    composite = (namespace, key)
    with _CACHE_LOCK:
        current = _INFLIGHT.get(composite)
        if current is not None and not current.done():
            return current
        active = sum(not future.done() for future in _INFLIGHT.values())
        if active >= _MAX_INFLIGHT:
            return None
        future = _EXECUTOR.submit(loader)
        _INFLIGHT[composite] = future

    def completed(done: Future[Any]) -> None:
        try:
            result = done.result()
            saver(result)
        except Exception:
            LOGGER.info("%s refresh failed for %s", namespace, key, exc_info=True)
        finally:
            with _CACHE_LOCK:
                if _INFLIGHT.get(composite) is done:
                    _INFLIGHT.pop(composite, None)

    future.add_done_callback(completed)
    return future


def _wait(future: Future[Any] | None, timeout: float) -> Any:
    if future is None:
        return None
    try:
        return future.result(timeout=max(0.05, timeout))
    except TimeoutError:
        return None
    except Exception:
        LOGGER.info("Interactive data loader failed", exc_info=True)
        return None


def _history_key(
    symbol: str,
    period: str | None,
    interval: str,
    years: int | None,
) -> tuple[str, str, str, int]:
    return (
        _normalized_symbol(symbol),
        str(period or "").strip().lower(),
        _normalized_interval(interval),
        int(years or 0),
    )


def peek_cached_history(
    symbol: str,
    *,
    period: str | None = None,
    interval: str = "1d",
    years: int | None = None,
    allow_stale: bool = True,
) -> pd.DataFrame:
    key = _history_key(symbol, period, interval, years)
    now = time.monotonic()
    with _CACHE_LOCK:
        item = _HISTORY_CACHE.get(key)
    if item is None:
        return pd.DataFrame()
    stored_at, frame = item
    age = now - stored_at
    if age <= _history_ttl(interval):
        return _mark_stale(frame, False)
    if allow_stale and age <= _history_stale_ttl(interval):
        return _mark_stale(frame, True)
    return pd.DataFrame()


def _history_saver(key: Hashable, value: Any) -> None:
    if not isinstance(value, pd.DataFrame) or value.empty:
        return
    with _CACHE_LOCK:
        _HISTORY_CACHE[key] = (time.monotonic(), _clone(value))


def _provider_wait_ms(frame: pd.DataFrame) -> float:
    attrs = dict(getattr(frame, "attrs", {}) or {})
    lineage = dict(attrs.get("data_lineage") or {})
    attempts = lineage.get("provider_attempts") or []
    total = 0.0
    for item in attempts:
        if isinstance(item, dict):
            try:
                total += float(item.get("elapsed_ms") or 0.0)
            except (TypeError, ValueError):
                continue
    return total


def _history_wrapper(original: Callable[..., Any]):
    def get_chart_history(
        symbol: str,
        period: str | None = None,
        interval: str = "1d",
        years: int = 5,
    ) -> pd.DataFrame:
        active = _active_history(symbol, interval)
        if active is not None:
            return active

        key = _history_key(symbol, period, interval, years)
        cached = peek_cached_history(
            symbol,
            period=period,
            interval=interval,
            years=years,
            allow_stale=True,
        )
        with _CACHE_LOCK:
            item = _HISTORY_CACHE.get(key)
        fresh = bool(
            item is not None
            and time.monotonic() - item[0] <= _history_ttl(interval)
        )
        if fresh:
            return cached

        def loader() -> pd.DataFrame:
            started = time.perf_counter()
            try:
                result = original(
                    symbol,
                    period=period,
                    interval=interval,
                    years=years,
                )
            except TypeError:
                result = original(symbol, period=period, interval=interval)
            elapsed = (time.perf_counter() - started) * 1000.0
            frame = result if isinstance(result, pd.DataFrame) else pd.DataFrame()
            record_phase(symbol, interval, "history_fetch_ms", elapsed)
            record_phase(
                symbol,
                interval,
                "provider_wait_ms",
                _provider_wait_ms(frame),
            )
            return frame

        future = _submit_once(
            "history",
            key,
            loader,
            lambda value: _history_saver(key, value),
        )
        if not cached.empty:
            return cached
        loaded = _wait(future, _HISTORY_BUDGET)
        if isinstance(loaded, pd.DataFrame) and not loaded.empty:
            _history_saver(key, loaded)
            return _mark_stale(loaded, False)
        return pd.DataFrame()

    get_chart_history.__name__ = "get_chart_history"
    get_chart_history._osoli_original = original  # type: ignore[attr-defined]
    return get_chart_history


def peek_cached_quote(symbol: str, *, allow_stale: bool = True) -> dict[str, Any]:
    key = _normalized_symbol(symbol)
    now = time.monotonic()
    with _CACHE_LOCK:
        item = _QUOTE_CACHE.get(key)
    if item is None:
        return {}
    stored_at, payload = item
    age = now - stored_at
    if age <= _quote_ttl():
        result = _clone(payload)
        result["is_stale"] = False
        result["cache_mode"] = "fresh"
        return result
    if allow_stale and age <= max(_quote_ttl() * 20.0, 3600.0):
        result = _clone(payload)
        result["is_stale"] = True
        result["cache_mode"] = "stale_while_revalidate"
        return result
    return {}


def _store_quote(symbol: str, payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    try:
        price = float(payload.get("price") or 0.0)
    except (TypeError, ValueError):
        price = 0.0
    if price <= 0:
        return
    with _CACHE_LOCK:
        _QUOTE_CACHE[_normalized_symbol(symbol)] = (
            time.monotonic(),
            _clone(payload),
        )


def _quote_wrapper(original: Callable[..., Any]):
    def fetch_batch_data(symbols_list: list) -> dict[str, dict[str, Any]]:
        requested = list(
            dict.fromkeys(
                _normalized_symbol(value)
                for value in symbols_list or []
                if _normalized_symbol(value)
            )
        )
        output: dict[str, dict[str, Any]] = {}
        missing: list[str] = []
        stale_found = False
        for symbol in requested:
            cached = peek_cached_quote(symbol, allow_stale=True)
            if cached:
                output[symbol] = cached
                stale_found = stale_found or bool(cached.get("is_stale"))
            else:
                missing.append(symbol)

        refresh_symbols = requested if stale_found else missing
        if not refresh_symbols:
            return output

        key = tuple(sorted(refresh_symbols))

        def loader() -> dict[str, dict[str, Any]]:
            started = time.perf_counter()
            result = original(list(refresh_symbols)) or {}
            elapsed = (time.perf_counter() - started) * 1000.0
            for symbol in refresh_symbols:
                record_phase(symbol, "quote", "header_quote_ms", elapsed)
            return result if isinstance(result, dict) else {}

        def saver(value: Any) -> None:
            if not isinstance(value, dict):
                return
            for symbol in refresh_symbols:
                payload = (
                    value.get(symbol)
                    or value.get(symbol.upper())
                    or value.get(symbol.replace(".SR", ""))
                    or {}
                )
                if isinstance(payload, dict):
                    _store_quote(symbol, payload)

        future = _submit_once("quotes", key, loader, saver)
        if output:
            return output
        loaded = _wait(future, _QUOTE_BUDGET)
        if isinstance(loaded, dict):
            saver(loaded)
        for symbol in requested:
            payload = peek_cached_quote(symbol, allow_stale=True)
            if payload:
                output[symbol] = payload
        return output

    fetch_batch_data.__name__ = "fetch_batch_data"
    fetch_batch_data._osoli_original = original  # type: ignore[attr-defined]
    return fetch_batch_data


def warm_quote_cache(symbol: str) -> None:
    try:
        import market_data

        market_data.fetch_batch_data([symbol])
    except Exception:
        LOGGER.debug("Quote warm-up failed for %s", symbol, exc_info=True)


def _tenant_key() -> tuple[int, int]:
    try:
        from tenant_scope import current_tenant

        tenant = current_tenant()
        if tenant is not None:
            return int(tenant.user_id), int(tenant.portfolio_id)
    except Exception:
        LOGGER.debug("Tenant lookup unavailable for financial cache", exc_info=True)
    return 0, 0


def _financial_wrapper(original: Callable[..., Any]):
    def get_stored_financials_df(
        symbol: str,
        period_type: str = "Annual",
    ) -> pd.DataFrame:
        key = (
            *_tenant_key(),
            _normalized_symbol(symbol),
            str(period_type or "Annual").strip().lower(),
        )
        now = time.monotonic()
        with _CACHE_LOCK:
            item = _FINANCIAL_CACHE.get(key)
        if item is not None:
            stored_at, frame, _lineage = item
            age = now - stored_at
            if age <= _financial_ttl():
                return _clone(frame)
            if age <= _financial_ttl() * 8.0:
                stale = _clone(frame)
                lineage = dict(
                    (getattr(stale, "attrs", {}) or {}).get(
                        "financial_lineage"
                    )
                    or {}
                )
                lineage["is_stale"] = True
                lineage["cache_mode"] = "stale_while_revalidate"
                stale.attrs["financial_lineage"] = lineage
                _submit_once(
                    "financial",
                    key,
                    lambda: original(symbol, period_type),
                    lambda value: _save_financial(key, value),
                )
                return stale

        started = time.perf_counter()
        future = _submit_once(
            "financial",
            key,
            lambda: original(symbol, period_type),
            lambda value: _save_financial(key, value),
        )
        loaded = _wait(future, _FINANCIAL_BUDGET)
        record_phase(
            symbol,
            "financial",
            "fundamental_ms",
            (time.perf_counter() - started) * 1000.0,
        )
        if isinstance(loaded, pd.DataFrame):
            _save_financial(key, loaded)
            return _clone(loaded)
        return pd.DataFrame()

    return get_stored_financials_df


def _save_financial(key: Hashable, value: Any) -> None:
    if not isinstance(value, pd.DataFrame):
        return
    lineage = dict(
        (getattr(value, "attrs", {}) or {}).get("financial_lineage") or {}
    )
    with _CACHE_LOCK:
        _FINANCIAL_CACHE[key] = (
            time.monotonic(),
            _clone(value),
            lineage,
        )


def _install_fast_twelvedata_adapters(providers: Any) -> None:
    session = getattr(providers, "_SESSION", None)
    if session is None:
        return

    def symbol_parts(symbol: str) -> tuple[str, str]:
        raw = _normalized_symbol(symbol).replace("^", "")
        raw = raw.replace("TADAWUL:", "").replace(".SR", "")
        if raw.isdigit():
            return raw, "XSAU"
        return ("TASI", "") if raw in {"TASI", "TADAWUL"} else (raw, "")

    def history(
        symbol: str,
        interval: str,
        years: int,
    ) -> tuple[pd.DataFrame, str]:
        key = providers._secret("TWELVEDATA_API_KEY")
        resolved, exchange = symbol_parts(symbol)
        if not key or not resolved:
            return pd.DataFrame(), resolved
        normalized = _normalized_interval(interval)
        td_interval = {
            "1m": "1min",
            "2m": "1min",
            "5m": "5min",
            "15m": "15min",
            "30m": "30min",
            "1h": "1h",
            "4h": "1h",
            "1d": "1day",
            "1wk": "1week",
            "1mo": "1month",
        }.get(normalized, normalized)
        outputsize = max(120, min(5000, analysis_row_limit(normalized) + 120))
        params: dict[str, Any] = {
            "symbol": resolved,
            "interval": td_interval,
            "outputsize": outputsize,
            "format": "JSON",
            "apikey": key,
        }
        if exchange:
            params["exchange"] = exchange
        payload, _reason = providers._request_json(
            "twelvedata",
            "https://api.twelvedata.com/time_series",
            params=params,
            timeout=max(1, int(round(_PROVIDER_TIMEOUT))),
        )
        frame = providers._frame_from_records(payload)
        if normalized == "2m" and not frame.empty:
            frame = providers._resample(frame, "2min")
        elif normalized == "4h" and not frame.empty:
            frame = providers._resample(frame, "4h")
        return frame, resolved

    def quote(symbol: str) -> tuple[dict[str, Any], str]:
        key = providers._secret("TWELVEDATA_API_KEY")
        resolved, exchange = symbol_parts(symbol)
        if not key or not resolved:
            return {}, resolved
        params: dict[str, Any] = {
            "symbol": resolved,
            "apikey": key,
        }
        if exchange:
            params["exchange"] = exchange
        payload, _reason = providers._request_json(
            "twelvedata",
            "https://api.twelvedata.com/quote",
            params=params,
            timeout=max(1, int(round(_PROVIDER_TIMEOUT))),
        )
        row = payload if isinstance(payload, dict) else {}
        return {
            "price": row.get("close") or row.get("price") or row.get("last"),
            "prev_close": row.get("previous_close") or row.get("prev_close"),
            "year_high": row.get("fifty_two_week", {}).get("high")
            if isinstance(row.get("fifty_two_week"), dict)
            else row.get("fifty_two_week_high"),
            "year_low": row.get("fifty_two_week", {}).get("low")
            if isinstance(row.get("fifty_two_week"), dict)
            else row.get("fifty_two_week_low"),
            "volume": row.get("volume"),
        }, resolved

    providers._HISTORY_ADAPTERS["twelvedata"] = history
    providers._QUOTE_ADAPTERS["twelvedata"] = quote


def _install_provider_limits() -> None:
    try:
        import market_providers_v5 as providers

        providers._MAX_RETRIES = 1  # noqa: SLF001
        original_request = providers._request_json  # noqa: SLF001
        if not getattr(original_request, "_osoli_bounded", False):

            def request_json(
                provider: str,
                url: str,
                *,
                params: dict[str, Any] | None = None,
                timeout: int = 12,
            ):
                bounded = min(float(timeout or _PROVIDER_TIMEOUT), _PROVIDER_TIMEOUT)
                return original_request(
                    provider,
                    url,
                    params=params,
                    timeout=max(1, int(round(bounded))),
                )

            request_json._osoli_bounded = True  # type: ignore[attr-defined]
            providers._request_json = request_json  # noqa: SLF001
        _install_fast_twelvedata_adapters(providers)
    except Exception:
        LOGGER.exception("Unable to install provider request limits")

    try:
        import market_data

        original_http = getattr(market_data, "_http_get", None)
        if callable(original_http) and not getattr(original_http, "_osoli_bounded", False):

            def http_get(
                url: str,
                timeout: int = 6,
                retries: int = 2,
                sleep: float = 0.6,
            ):
                return original_http(
                    url,
                    timeout=min(int(timeout or 3), 3),
                    retries=0,
                    sleep=min(float(sleep or 0.0), 0.2),
                )

            http_get._osoli_bounded = True  # type: ignore[attr-defined]
            market_data._http_get = http_get
    except Exception:
        LOGGER.exception("Unable to cap legacy HTTP waits")


def install_performance_runtime() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        _install_provider_limits()

        import market_data

        history = market_data.get_chart_history
        if not getattr(history, "_osoli_performance_v7", False):
            wrapped_history = _history_wrapper(history)
            wrapped_history._osoli_performance_v7 = True  # type: ignore[attr-defined]
            market_data.get_chart_history = wrapped_history

        batch = market_data.fetch_batch_data
        if not getattr(batch, "_osoli_performance_v7", False):
            wrapped_batch = _quote_wrapper(batch)
            wrapped_batch._osoli_performance_v7 = True  # type: ignore[attr-defined]
            market_data.fetch_batch_data = wrapped_batch

        try:
            import financial_analysis.store as store

            financial = store.get_stored_financials_df
            if not getattr(financial, "_osoli_performance_v7", False):
                wrapped_financial = _financial_wrapper(financial)
                wrapped_financial._osoli_performance_v7 = True  # type: ignore[attr-defined]
                store.get_stored_financials_df = wrapped_financial

                for module_name in (
                    "financial_analysis.metrics",
                    "financial_analysis.data_quality",
                    "financial_analysis.ui",
                ):
                    try:
                        module = __import__(module_name, fromlist=["*"])
                        if hasattr(module, "get_stored_financials_df"):
                            module.get_stored_financials_df = wrapped_financial
                    except Exception:
                        LOGGER.debug(
                            "Deferred financial binding patch: %s",
                            module_name,
                            exc_info=True,
                        )
        except Exception:
            LOGGER.exception("Unable to install financial cache")

        market_data.performance_status_v7 = performance_status
        _INSTALLED = True


def performance_status() -> dict[str, Any]:
    with _CACHE_LOCK:
        return {
            "installed": _INSTALLED,
            "history_entries": len(_HISTORY_CACHE),
            "quote_entries": len(_QUOTE_CACHE),
            "financial_entries": len(_FINANCIAL_CACHE),
            "inflight": sum(not value.done() for value in _INFLIGHT.values()),
            "max_workers": _MAX_WORKERS,
            "max_inflight": _MAX_INFLIGHT,
            "budgets_seconds": {
                "history": _HISTORY_BUDGET,
                "quote": _QUOTE_BUDGET,
                "financial": _FINANCIAL_BUDGET,
                "provider_request": _PROVIDER_TIMEOUT,
            },
            "captured_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
        }


__all__ = [
    "activate_history",
    "analysis_row_limit",
    "clear_performance_trace",
    "deactivate_history",
    "install_performance_runtime",
    "peek_cached_history",
    "peek_cached_quote",
    "performance_status",
    "performance_trace",
    "record_phase",
    "warm_quote_cache",
]
