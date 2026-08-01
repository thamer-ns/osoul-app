"""One reusable analysis context per symbol/timeframe and report execution."""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

import pandas as pd

from candle_confirmation import completed_candles
from performance_runtime_v7 import (
    activate_history,
    analysis_row_limit,
    clear_performance_trace,
    deactivate_history,
    performance_trace,
    record_phase,
)

LOGGER = logging.getLogger(__name__)
_INSTALL_LOCK = threading.RLock()
_CACHE_LOCK = threading.RLock()
_INSTALLED = False
_CONTEXT_CACHE: dict[
    tuple[int, int, str, str, str],
    tuple[float, "AnalysisContext"],
] = {}
_ORIGINAL_INDICATORS = None
_ORIGINAL_FINANCIAL = None
_ACTIVE_CONTEXT: ContextVar["AnalysisContext | None"] = ContextVar(
    "osoli_analysis_context", default=None
)


@dataclass(slots=True)
class AnalysisContext:
    symbol: str
    timeframe: str
    interval: str
    period: str
    history: pd.DataFrame
    closed_history: pd.DataFrame
    indicators: dict[str, Any]
    fingerprint: str
    timings: dict[str, float] = field(default_factory=dict)


def _tenant_key() -> tuple[int, int]:
    try:
        from tenant_scope import current_tenant

        tenant = current_tenant()
        if tenant is not None:
            return int(tenant.user_id), int(tenant.portfolio_id)
    except Exception:
        LOGGER.debug("Context tenant lookup unavailable", exc_info=True)
    return 0, 0


def _interval(timeframe: str) -> str:
    from ai_engine_core.reporting_policy_v5 import timeframe_to_interval

    return timeframe_to_interval(timeframe)


def _period(timeframe: str) -> str:
    from ai_engine_core.core import _map_period_from_timeframe

    return str(_map_period_from_timeframe(timeframe) or "5y")


def _fingerprint(frame: pd.DataFrame) -> str:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return "empty"
    last_index = str(frame.index[-1])
    try:
        last_close = float(
            pd.to_numeric(frame["Close"], errors="coerce").iloc[-1]
        )
    except Exception:
        last_close = 0.0
    raw = f"{len(frame)}|{last_index}|{last_close:.10f}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _trim(frame: pd.DataFrame, interval: str) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    limit = analysis_row_limit(interval)
    output = frame.tail(limit).copy(deep=True)
    output.attrs.update(dict(getattr(frame, "attrs", {}) or {}))
    output.attrs["analysis_window"] = {
        "input_rows": int(len(frame)),
        "used_rows": int(len(output)),
        "limit": int(limit),
        "interval": str(interval),
    }
    return output


def _copy_context(value: AnalysisContext) -> AnalysisContext:
    history = value.history.copy(deep=True)
    history.attrs.update(dict(getattr(value.history, "attrs", {}) or {}))
    closed = value.closed_history.copy(deep=True)
    closed.attrs.update(dict(getattr(value.closed_history, "attrs", {}) or {}))
    return AnalysisContext(
        symbol=value.symbol,
        timeframe=value.timeframe,
        interval=value.interval,
        period=value.period,
        history=history,
        closed_history=closed,
        indicators=dict(value.indicators),
        fingerprint=value.fingerprint,
        timings=dict(value.timings),
    )


def _compatible_cached_history(symbol: str, interval: str) -> pd.DataFrame:
    """Reuse a valid hot-cache frame even when its requested period differs."""
    try:
        from sc_runtime_v9 import peek_latest_cached_history

        value = peek_latest_cached_history(
            symbol,
            interval=interval,
            allow_stale=True,
        )
        if isinstance(value, pd.DataFrame) and not value.empty:
            record_phase(symbol, interval, "compatible_history_cache_hit", 1.0)
            return value
    except Exception:
        LOGGER.debug("Compatible history cache lookup failed", exc_info=True)
    return pd.DataFrame()


def _seed_history_cache(
    symbol: str,
    period: str,
    interval: str,
    frame: pd.DataFrame,
) -> None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return
    try:
        import performance_runtime_v7 as runtime

        key = runtime._history_key(  # noqa: SLF001
            symbol,
            period,
            interval,
            5,
        )
        runtime._history_saver(key, frame)  # noqa: SLF001
    except Exception:
        LOGGER.debug("Unable to seed rescued analysis history", exc_info=True)


def _rescue_history(
    symbol: str,
    period: str,
    interval: str,
) -> pd.DataFrame:
    """Use one independent bounded Yahoo Chart request after routed failure."""
    from analysis_history_rescue_v21 import fetch_yahoo_history_rescue

    started = time.perf_counter()
    frame, diagnostic = fetch_yahoo_history_rescue(
        symbol,
        period=period,
        interval=interval,
    )
    elapsed = (time.perf_counter() - started) * 1000.0
    record_phase(symbol, interval, "history_rescue_ms", elapsed)
    record_phase(
        symbol,
        interval,
        "history_rescue_ok",
        1.0 if not frame.empty else 0.0,
    )
    if frame.empty:
        LOGGER.warning(
            "Analysis history rescue failed for %s %s: %s",
            symbol,
            interval,
            diagnostic.get("reason") or "unknown",
        )
        return pd.DataFrame()
    _seed_history_cache(symbol, period, interval, frame)
    return frame


def build_analysis_context(
    symbol: str,
    timeframe: str = "1D",
    *,
    refresh: bool = False,
) -> AnalysisContext:
    install_analysis_context()
    from ai_engine_core.core import _normalize_symbol
    from market_data import get_chart_history

    normalized = _normalize_symbol(symbol)
    interval = _interval(timeframe)
    period = _period(timeframe)
    if refresh:
        clear_performance_trace(normalized, interval)

    started = time.perf_counter()
    try:
        history = get_chart_history(
            normalized,
            period=period,
            interval=interval,
        )
    except TypeError:
        history = get_chart_history(normalized, period=period)
    history = history if isinstance(history, pd.DataFrame) else pd.DataFrame()
    history_ms = (time.perf_counter() - started) * 1000.0
    record_phase(normalized, interval, "history_fetch_ms", history_ms)

    if history.empty:
        history = _compatible_cached_history(normalized, interval)
    if history.empty:
        history = _rescue_history(normalized, period, interval)

    if history.empty:
        return AnalysisContext(
            symbol=normalized,
            timeframe=str(timeframe),
            interval=interval,
            period=period,
            history=pd.DataFrame(),
            closed_history=pd.DataFrame(),
            indicators={},
            fingerprint="empty",
            timings=performance_trace(normalized, interval),
        )

    prepared = _trim(history, interval)
    closed = completed_candles(prepared, interval=interval)
    closed = _trim(closed, interval)
    fingerprint = _fingerprint(closed)
    key = (*_tenant_key(), normalized, interval, fingerprint)
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CONTEXT_CACHE.get(key)
    if not refresh and cached is not None and now - cached[0] <= 300.0:
        return _copy_context(cached[1])

    indicator_started = time.perf_counter()
    compute = _ORIGINAL_INDICATORS
    indicators = compute(closed) if callable(compute) and not closed.empty else {}
    indicator_ms = (time.perf_counter() - indicator_started) * 1000.0
    record_phase(normalized, interval, "basic_indicators_ms", indicator_ms)
    context = AnalysisContext(
        symbol=normalized,
        timeframe=str(timeframe),
        interval=interval,
        period=period,
        history=prepared,
        closed_history=closed,
        indicators=indicators if isinstance(indicators, dict) else {},
        fingerprint=fingerprint,
        timings=performance_trace(normalized, interval),
    )
    with _CACHE_LOCK:
        _CONTEXT_CACHE[key] = (now, _copy_context(context))
        if len(_CONTEXT_CACHE) > 256:
            oldest = sorted(
                _CONTEXT_CACHE.items(),
                key=lambda item: item[1][0],
            )[:32]
            for old_key, _value in oldest:
                _CONTEXT_CACHE.pop(old_key, None)
    return context


@contextmanager
def active_context(context: AnalysisContext) -> Iterator[None]:
    history_token = activate_history(
        context.symbol,
        context.interval,
        context.history,
    )
    context_token = _ACTIVE_CONTEXT.set(context)
    try:
        yield
    finally:
        _ACTIVE_CONTEXT.reset(context_token)
        deactivate_history(history_token)


def _context_indicators(frame: pd.DataFrame) -> dict[str, Any]:
    context = _ACTIVE_CONTEXT.get()
    if context is not None and _fingerprint(frame) == context.fingerprint:
        return context.indicators
    return _ORIGINAL_INDICATORS(frame) if callable(_ORIGINAL_INDICATORS) else {}


_FINANCIAL_CACHE: dict[
    tuple[int, int, str],
    tuple[float, tuple[Any, Any, Any]],
] = {}


def _cached_financial(symbol: str):
    key = (*_tenant_key(), str(symbol or "").strip().upper())
    now = time.monotonic()
    with _CACHE_LOCK:
        item = _FINANCIAL_CACHE.get(key)
    if item is not None and now - item[0] <= 6 * 3600.0:
        return item[1]
    started = time.perf_counter()
    result = (
        _ORIGINAL_FINANCIAL(symbol)
        if callable(_ORIGINAL_FINANCIAL)
        else (0, [], {})
    )
    record_phase(
        symbol,
        "financial",
        "fundamental_ms",
        (time.perf_counter() - started) * 1000.0,
    )
    with _CACHE_LOCK:
        _FINANCIAL_CACHE[key] = (now, result)
    return result


def install_analysis_context() -> None:
    global _INSTALLED, _ORIGINAL_INDICATORS, _ORIGINAL_FINANCIAL
    if _INSTALLED:
        return
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        from ai_engine_core import reporting

        _ORIGINAL_INDICATORS = reporting._compute_indicators
        _ORIGINAL_FINANCIAL = reporting._analyze_financial_golden_rules
        reporting._compute_indicators = _context_indicators
        reporting._analyze_financial_golden_rules = _cached_financial
        reporting._analysis_context_v7_installed = True
        _INSTALLED = True


def generate_with_context(
    raw_generator,
    symbol: str,
    timeframe: str,
    *,
    refresh: bool = False,
) -> tuple[dict[str, Any], AnalysisContext]:
    total_started = time.perf_counter()
    context = build_analysis_context(symbol, timeframe, refresh=refresh)
    if context.closed_history.empty:
        return (
            {
                "ok": False,
                "status": "error",
                "symbol": context.symbol,
                "timeframe": timeframe,
                "error": "no_data_within_budget",
                "diagnostic_code": "analysis_history_unavailable",
                "retryable": True,
                "message": (
                    "تعذر جلب شموع تاريخية كافية من المصادر الحالية. "
                    "لم تُنشأ صفقة أو توصية ناقصة، ويمكن إعادة المحاولة."
                ),
                "performance": performance_trace(
                    context.symbol,
                    context.interval,
                ),
            },
            context,
        )
    with active_context(context):
        raw = raw_generator(context.symbol, timeframe=timeframe)
    report = raw if isinstance(raw, dict) else {}
    total_ms = (time.perf_counter() - total_started) * 1000.0
    record_phase(context.symbol, context.interval, "total_analysis_ms", total_ms)
    timings = performance_trace(context.symbol, context.interval)
    report["performance"] = timings
    engine_meta = report.get("engine_meta")
    if not isinstance(engine_meta, dict):
        engine_meta = {}
    lineage = dict(
        (getattr(context.history, "attrs", {}) or {}).get("data_lineage")
        or {}
    )
    engine_meta["performance"] = timings
    engine_meta["analysis_context"] = {
        "fingerprint": context.fingerprint,
        "history_rows": int(len(context.history)),
        "closed_rows": int(len(context.closed_history)),
        "window_limit": analysis_row_limit(context.interval),
        "history_reused": True,
        "indicators_reused": True,
        "history_source": str(
            lineage.get("source")
            or getattr(context.history, "attrs", {}).get("source")
            or "unknown"
        ),
        "cold_start_rescue": bool(lineage.get("cold_start_rescue")),
    }
    report["engine_meta"] = engine_meta
    return report, context


__all__ = [
    "AnalysisContext",
    "active_context",
    "build_analysis_context",
    "generate_with_context",
    "install_analysis_context",
]
