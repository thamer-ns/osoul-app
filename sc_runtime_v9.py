"""Osoli V9 runtime hardening on top of the SC-V8 analysis contract.

This layer closes the remaining latency and correctness gaps without changing
public analysis APIs:
- persistent market writes are coalesced on one bounded background worker;
- mixed cached/uncached quote batches wait only for the missing subset;
- cache lookup can reuse any compatible period for an already loaded symbol;
- analysis history periods are derived from the resolved interval;
- the SC-V91 role-reversal volume gate is installed before analysis views bind.
"""
from __future__ import annotations

import copy
import logging
import math
import os
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Hashable

import pandas as pd

import persistent_market_cache_v8 as persistent_cache
from ai_engine_core.breakout_patterns_v91 import install_breakout_patterns_v91

LOGGER = logging.getLogger(__name__)
_INSTALL_LOCK = threading.RLock()
_INSTALLED = False
_PERSIST_LOCK = threading.RLock()
_PERSIST_EXECUTOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="osoli-persist-v9",
)
_PERSIST_PENDING: OrderedDict[
    tuple[str, Hashable],
    tuple[str, Hashable, Any, float],
] = OrderedDict()
_PERSIST_RUNNING = False
_PERSIST_MAX_PENDING = max(
    32,
    min(2048, int(os.getenv("OSOUL_PERSIST_MAX_PENDING", "512"))),
)


def _clone_frame(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy(deep=True)
    output.attrs.update(copy.deepcopy(dict(getattr(frame, "attrs", {}) or {})))
    return output


def _drain_persistent_writes() -> None:
    global _PERSIST_RUNNING
    while True:
        with _PERSIST_LOCK:
            if not _PERSIST_PENDING:
                _PERSIST_RUNNING = False
                return
            _queue_key, task = _PERSIST_PENDING.popitem(last=False)
        kind, key, value, ttl_seconds = task
        try:
            if kind == "history":
                persistent_cache.save_history(
                    key,
                    value,
                    ttl_seconds=ttl_seconds,
                )
            else:
                persistent_cache.save_quote(
                    str(key),
                    value,
                    ttl_seconds=ttl_seconds,
                )
        except Exception:
            LOGGER.info("Persistent %s write failed for %s", kind, key, exc_info=True)


def _enqueue_persistent(
    kind: str,
    key: Hashable,
    value: Any,
    ttl_seconds: float,
) -> None:
    global _PERSIST_RUNNING
    queue_key = (kind, key)
    with _PERSIST_LOCK:
        _PERSIST_PENDING.pop(queue_key, None)
        _PERSIST_PENDING[queue_key] = (
            kind,
            key,
            value,
            max(1.0, float(ttl_seconds)),
        )
        while len(_PERSIST_PENDING) > _PERSIST_MAX_PENDING:
            _PERSIST_PENDING.popitem(last=False)
        if _PERSIST_RUNNING:
            return
        _PERSIST_RUNNING = True
        _PERSIST_EXECUTOR.submit(_drain_persistent_writes)


def _install_nonblocking_persistence() -> None:
    import performance_runtime_v7 as runtime

    def history_saver(key: Hashable, value: Any) -> None:
        if not isinstance(value, pd.DataFrame) or value.empty:
            return
        frame = _clone_frame(value)
        with runtime._CACHE_LOCK:  # noqa: SLF001
            runtime._HISTORY_CACHE[key] = (  # noqa: SLF001
                time.monotonic(),
                runtime._clone(frame),  # noqa: SLF001
            )
        interval = (
            str(key[2])
            if isinstance(key, tuple) and len(key) > 2
            else "1d"
        )
        _enqueue_persistent(
            "history",
            key,
            frame,
            runtime._history_stale_ttl(interval),  # noqa: SLF001
        )

    def store_quote(symbol: str, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        try:
            price = float(payload.get("price") or 0.0)
        except (TypeError, ValueError, OverflowError):
            return
        if not math.isfinite(price) or price <= 0:
            return
        normalized = runtime._normalized_symbol(symbol)  # noqa: SLF001
        clean = runtime._clone(payload)  # noqa: SLF001
        with runtime._CACHE_LOCK:  # noqa: SLF001
            runtime._QUOTE_CACHE[normalized] = (  # noqa: SLF001
                time.monotonic(),
                runtime._clone(clean),  # noqa: SLF001
            )
        _enqueue_persistent(
            "quote",
            normalized,
            clean,
            max(runtime._quote_ttl() * 20.0, 3600.0),  # noqa: SLF001
        )

    history_saver._osoli_nonblocking_v9 = True  # type: ignore[attr-defined]
    store_quote._osoli_nonblocking_v9 = True  # type: ignore[attr-defined]
    runtime._history_saver = history_saver  # noqa: SLF001
    runtime._store_quote = store_quote  # noqa: SLF001


def _install_corrected_quote_batch() -> None:
    import market_data
    import performance_runtime_v7 as runtime

    current = market_data.fetch_batch_data
    if getattr(current, "_osoli_mixed_batch_v9", False):
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
        stale_found = False
        for symbol in requested:
            cached = runtime.peek_cached_quote(symbol, allow_stale=True)
            if cached:
                output[symbol] = cached
                stale_found = stale_found or bool(cached.get("is_stale"))
            else:
                missing.append(symbol)

        refresh_symbols = requested if stale_found else missing
        if not refresh_symbols:
            return output

        def loader() -> dict[str, dict[str, Any]]:
            started = time.perf_counter()
            result = provider_batch(list(refresh_symbols)) or {}
            elapsed = (time.perf_counter() - started) * 1000.0
            for symbol in refresh_symbols:
                runtime.record_phase(symbol, "quote", "header_quote_ms", elapsed)
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
                    runtime._store_quote(symbol, payload)  # noqa: SLF001

        key = tuple(sorted(refresh_symbols))
        future = runtime._submit_once("quotes", key, loader, saver)  # noqa: SLF001
        # Return immediately only when every requested symbol already has a usable
        # value. A mixed batch waits within the quote budget for its missing subset.
        if not missing:
            return output
        loaded = runtime._wait(future, runtime._QUOTE_BUDGET)  # noqa: SLF001
        if isinstance(loaded, dict):
            saver(loaded)
        for symbol in requested:
            payload = runtime.peek_cached_quote(symbol, allow_stale=True)
            if payload:
                output[symbol] = payload
        return output

    fetch_batch_data.__name__ = "fetch_batch_data"
    fetch_batch_data._osoli_original = provider_batch  # type: ignore[attr-defined]
    fetch_batch_data._osoli_mixed_batch_v9 = True  # type: ignore[attr-defined]
    market_data.fetch_batch_data = fetch_batch_data


def peek_latest_cached_history(
    symbol: str,
    *,
    interval: str = "1d",
    allow_stale: bool = True,
) -> pd.DataFrame:
    """Return the newest compatible hot-cache entry regardless of period key."""
    import performance_runtime_v7 as runtime

    normalized_symbol = runtime._normalized_symbol(symbol)  # noqa: SLF001
    normalized_interval = runtime._normalized_interval(interval)  # noqa: SLF001
    now = time.monotonic()
    candidates: list[tuple[float, pd.DataFrame]] = []
    with runtime._CACHE_LOCK:  # noqa: SLF001
        items = list(runtime._HISTORY_CACHE.items())  # noqa: SLF001
    for key, item in items:
        if not isinstance(key, tuple) or len(key) < 3:
            continue
        if (
            str(key[0]) != normalized_symbol
            or runtime._normalized_interval(key[2]) != normalized_interval  # noqa: SLF001
        ):
            continue
        stored_at, frame = item
        age = now - float(stored_at)
        fresh_limit = runtime._history_ttl(normalized_interval)  # noqa: SLF001
        stale_limit = runtime._history_stale_ttl(normalized_interval)  # noqa: SLF001
        if age <= fresh_limit or (allow_stale and age <= stale_limit):
            candidates.append((float(stored_at), frame))
    if not candidates:
        return pd.DataFrame()
    stored_at, frame = max(candidates, key=lambda item: item[0])
    stale = now - stored_at > runtime._history_ttl(normalized_interval)  # noqa: SLF001
    return runtime._mark_stale(frame, stale)  # noqa: SLF001


def _install_interval_period_policy() -> None:
    import analysis_context_v7 as context

    def period(timeframe: str) -> str:
        interval = context._interval(timeframe)  # noqa: SLF001
        return {
            "1m": "7d",
            "2m": "60d",
            "5m": "60d",
            "15m": "60d",
            "30m": "60d",
            "60m": "2y",
            "1h": "2y",
            "4h": "5y",
            "1d": "5y",
            "1wk": "15y",
            "1w": "15y",
            "1mo": "20y",
        }.get(str(interval).lower(), "5y")

    period._osoli_interval_period_v9 = True  # type: ignore[attr-defined]
    context._period = period  # noqa: SLF001


def runtime_status() -> dict[str, Any]:
    from sc_runtime_v8 import runtime_status as runtime_status_v8

    status = dict(runtime_status_v8())
    with _PERSIST_LOCK:
        pending = len(_PERSIST_PENDING)
        running = _PERSIST_RUNNING
    status.update(
        {
            "runtime_version": "9.0",
            "persistent_writes_background_only": True,
            "persistent_writer_threads": 1,
            "persistent_pending": pending,
            "persistent_writer_running": running,
            "persistent_max_pending": _PERSIST_MAX_PENDING,
            "mixed_quote_batches_fixed": True,
            "interval_period_policy": True,
            "role_reversal_volume_gate": "SC-V91",
        }
    )
    return status


def install_sc_runtime_v9() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        from persistent_cache_resilience_v10 import (
            install_persistent_cache_resilience_v10,
        )

        # Patch optional cache operations before V8 imports them by value.
        install_persistent_cache_resilience_v10()

        from ai_engine_core.reporting_policy_v5 import install_reporting_policy
        from analysis_context_v7 import install_analysis_context
        from bounded_twelvedata_v9 import install_bounded_twelvedata_v9
        from market_data_router_v5 import install_market_data_router
        from performance_runtime_v7 import install_performance_runtime
        from sc_runtime_v8 import install_sc_runtime_v8

        install_reporting_policy()
        install_market_data_router()
        install_performance_runtime()
        install_analysis_context()
        install_bounded_twelvedata_v9()
        install_sc_runtime_v8()
        _install_nonblocking_persistence()
        _install_corrected_quote_batch()
        _install_interval_period_policy()
        install_breakout_patterns_v91()
        _INSTALLED = True


__all__ = [
    "install_sc_runtime_v9",
    "peek_latest_cached_history",
    "runtime_status",
]
