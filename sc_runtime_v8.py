"""Install the SC feature pack and the low-latency market runtime.

The installer preserves v7 public APIs while separating slow workloads,
preventing hidden executor queues, enforcing a total provider deadline,
restoring the last valid public-market snapshot after process restarts and
adding one deterministic SC-V90/SC-FXM contract to every generated report.
"""
from __future__ import annotations

import copy
import logging
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Callable, Hashable

import pandas as pd

from ai_engine_core.sc_feature_pack_v8 import (
    SC_FEATURE_VERSION,
    build_sc_feature_pack,
)
from persistent_market_cache_v8 import (
    install_persistent_market_cache,
    load_history,
    load_quote,
    prune_expired,
    save_history,
    save_quote,
)

LOGGER = logging.getLogger(__name__)
_INSTALL_LOCK = threading.RLock()
_INSTALLED = False
_PROVIDER_LOCK = threading.RLock()
_PROVIDER_STATS: dict[str, dict[str, float]] = {}
_REQUEST_DEADLINE: ContextVar[float | None] = ContextVar(
    "osoli_provider_deadline_v8",
    default=None,
)
_HISTORY_DEADLINE = max(
    1.5,
    float(os.getenv("OSOUL_HISTORY_TOTAL_DEADLINE_SECONDS", "4.5")),
)
_QUOTE_DEADLINE = max(
    0.8,
    float(os.getenv("OSOUL_QUOTE_TOTAL_DEADLINE_SECONDS", "2.4")),
)
_POOL_SIZES = {
    "history": max(1, min(4, int(os.getenv("OSOUL_HISTORY_WORKERS", "2")))),
    "quotes": max(1, min(8, int(os.getenv("OSOUL_QUOTE_WORKERS", "4")))),
    "financial": max(1, min(4, int(os.getenv("OSOUL_FINANCIAL_WORKERS", "2")))),
    "default": 2,
}
_EXECUTORS = {
    name: ThreadPoolExecutor(
        max_workers=size,
        thread_name_prefix=f"osoli-{name}-v8",
    )
    for name, size in _POOL_SIZES.items()
}


def _remaining(default: float) -> float:
    deadline = _REQUEST_DEADLINE.get()
    if deadline is None:
        return default
    return max(0.0, deadline - time.monotonic())


def _record_provider(provider: str, *, ok: bool, elapsed_ms: float) -> None:
    with _PROVIDER_LOCK:
        state = _PROVIDER_STATS.setdefault(
            provider,
            {
                "ewma_ms": max(1.0, elapsed_ms),
                "successes": 0.0,
                "failures": 0.0,
            },
        )
        state["ewma_ms"] = (
            state["ewma_ms"] * 0.72 + max(1.0, elapsed_ms) * 0.28
        )
        if ok:
            state["successes"] += 1.0
            state["failures"] = max(0.0, state["failures"] - 0.25)
        else:
            state["failures"] += 1.0


def _ranked_order(providers: Any) -> list[str]:
    base = list(providers.configured_provider_order())
    with _PROVIDER_LOCK:
        stats = copy.deepcopy(_PROVIDER_STATS)
    status = {
        str(row.get("provider")): row
        for row in providers.provider_status()
        if isinstance(row, dict)
    }
    positions = {provider: index for index, provider in enumerate(base)}

    def rank(provider: str) -> tuple[float, float, float, int]:
        health = status.get(provider) or {}
        metric = stats.get(provider) or {}
        open_penalty = 1.0 if health.get("circuit_open") else 0.0
        failures = float(
            metric.get("failures") or health.get("failures") or 0.0
        )
        observed = float(metric.get("successes") or 0.0) + failures
        latency = (
            float(metric.get("ewma_ms") or 50_000.0)
            if observed >= 2
            else 50_000.0
        )
        return open_penalty, failures, latency, positions.get(provider, 99)

    return sorted(base, key=rank)


def _install_provider_deadlines() -> None:
    import market_data_router_v5 as router
    import market_providers_v5 as providers

    original_request = providers._request_json  # noqa: SLF001
    if not getattr(original_request, "_osoli_total_deadline_v8", False):

        def request_json(
            provider: str,
            url: str,
            *,
            params: dict[str, Any] | None = None,
            timeout: int = 12,
        ):
            remaining = _remaining(float(timeout or 1))
            if remaining < 0.20:
                return None, "total_deadline_exceeded"
            bounded = max(
                1,
                int(min(float(timeout or 1), remaining) + 0.999),
            )
            return original_request(
                provider,
                url,
                params=params,
                timeout=bounded,
            )

        request_json._osoli_total_deadline_v8 = True  # type: ignore[attr-defined]
        providers._request_json = request_json  # noqa: SLF001

    def fetch_history(
        symbol: str,
        *,
        interval: str = "1d",
        years: int = 5,
        minimum_rows: int = 20,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        attempts: list[Any] = []
        token = _REQUEST_DEADLINE.set(time.monotonic() + _HISTORY_DEADLINE)
        try:
            for provider in _ranked_order(providers):
                if _remaining(0.0) < 0.20:
                    attempts.append(
                        providers.ProviderAttempt(
                            provider,
                            False,
                            "total_deadline_exceeded",
                        )
                    )
                    break
                if not providers._secret(  # noqa: SLF001
                    providers._SECRET_NAMES[provider]  # noqa: SLF001
                ):
                    attempts.append(
                        providers.ProviderAttempt(
                            provider,
                            False,
                            "not_configured",
                        )
                    )
                    continue
                started = time.perf_counter()
                reason = ""
                try:
                    frame, resolved = providers._HISTORY_ADAPTERS[provider](  # noqa: SLF001
                        symbol,
                        interval,
                        years,
                    )
                except Exception as exc:
                    LOGGER.info(
                        "%s bounded history adapter failed",
                        provider,
                        exc_info=True,
                    )
                    frame, resolved = pd.DataFrame(), ""
                    reason = type(exc).__name__.lower()
                elapsed = (time.perf_counter() - started) * 1000.0
                quality = providers.validate_ohlcv(
                    frame,
                    minimum_rows=minimum_rows,
                )
                ok = bool(quality["ok"])
                _record_provider(provider, ok=ok, elapsed_ms=elapsed)
                attempts.append(
                    providers.ProviderAttempt(
                        provider,
                        ok,
                        reason
                        or (
                            ""
                            if ok
                            else ";".join(quality["issues"])
                        ),
                        rows=int(quality["rows"]),
                        resolved_symbol=resolved,
                        elapsed_ms=round(elapsed),
                        quality_score=int(quality["score"]),
                    )
                )
                if not ok:
                    continue
                output = frame.copy(deep=True)
                fetched_at = (
                    datetime.now(timezone.utc)
                    .replace(microsecond=0)
                    .isoformat()
                )
                lineage = {
                    "source": provider,
                    "symbol": str(symbol),
                    "resolved_symbol": resolved,
                    "interval": providers.normalize_interval(interval),
                    "rows": int(len(output)),
                    "start": str(output.index.min()),
                    "end": str(output.index.max()),
                    "fetched_at": fetched_at,
                    "quality_score": int(quality["score"]),
                    "provider_attempts": [
                        item.as_dict() for item in attempts
                    ],
                    "provider_order": _ranked_order(providers),
                    "is_stale": False,
                    "fusion_version": "8.0",
                    "total_deadline_seconds": _HISTORY_DEADLINE,
                }
                output.attrs["source"] = provider
                output.attrs["data_lineage"] = lineage
                return output, [item.as_dict() for item in attempts]
            return pd.DataFrame(), [item.as_dict() for item in attempts]
        finally:
            _REQUEST_DEADLINE.reset(token)

    def fetch_quote(
        symbol: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        attempts: list[dict[str, Any]] = []
        token = _REQUEST_DEADLINE.set(time.monotonic() + _QUOTE_DEADLINE)
        try:
            for provider in _ranked_order(providers):
                if _remaining(0.0) < 0.15:
                    attempts.append(
                        {
                            "provider": provider,
                            "ok": False,
                            "reason": "total_deadline_exceeded",
                        }
                    )
                    break
                if not providers._secret(  # noqa: SLF001
                    providers._SECRET_NAMES[provider]  # noqa: SLF001
                ):
                    attempts.append(
                        {
                            "provider": provider,
                            "ok": False,
                            "reason": "not_configured",
                        }
                    )
                    continue
                started = time.perf_counter()
                try:
                    raw, resolved = providers._QUOTE_ADAPTERS[provider](  # noqa: SLF001
                        symbol
                    )
                except Exception:
                    LOGGER.info(
                        "%s bounded quote adapter failed",
                        provider,
                        exc_info=True,
                    )
                    raw, resolved = {}, ""
                price = providers._finite_positive(  # noqa: SLF001
                    raw.get("price")
                )
                previous = providers._finite_positive(  # noqa: SLF001
                    raw.get("prev_close")
                )
                elapsed = (time.perf_counter() - started) * 1000.0
                ok = price is not None
                _record_provider(provider, ok=ok, elapsed_ms=elapsed)
                attempts.append(
                    {
                        "provider": provider,
                        "ok": ok,
                        "reason": "" if ok else "invalid_or_missing_price",
                        "resolved_symbol": resolved,
                        "elapsed_ms": round(elapsed),
                    }
                )
                if not ok:
                    continue
                change = (
                    ((price - previous) / previous) * 100.0
                    if previous
                    else None
                )
                return {
                    "symbol": str(symbol),
                    "resolved_symbol": resolved,
                    "price": price,
                    "prev_close": previous,
                    "previous_close": previous,
                    "change_pct": (
                        round(change, 4) if change is not None else None
                    ),
                    "change_percent": (
                        round(change, 4) if change is not None else None
                    ),
                    "change_available": change is not None,
                    "year_high": providers._finite_positive(  # noqa: SLF001
                        raw.get("year_high")
                    ),
                    "year_low": providers._finite_positive(  # noqa: SLF001
                        raw.get("year_low")
                    ),
                    "volume": providers._finite_positive(  # noqa: SLF001
                        raw.get("volume")
                    ),
                    "source": provider,
                    "fetched_at": (
                        datetime.now(timezone.utc)
                        .replace(microsecond=0)
                        .isoformat()
                    ),
                    "is_stale": False,
                    "provider_attempts": attempts,
                    "fusion_version": "8.0",
                    "total_deadline_seconds": _QUOTE_DEADLINE,
                }, attempts
            return {}, attempts
        finally:
            _REQUEST_DEADLINE.reset(token)

    fetch_history._osoli_bounded_v8 = True  # type: ignore[attr-defined]
    fetch_quote._osoli_bounded_v8 = True  # type: ignore[attr-defined]
    providers.fetch_history = fetch_history
    providers.fetch_quote = fetch_quote
    # The router imported both functions directly; update those globals too.
    router.fetch_history = fetch_history
    router.fetch_quote = fetch_quote


def _install_priority_executors() -> None:
    import performance_runtime_v7 as runtime

    def submit_once(
        namespace: str,
        key: Hashable,
        loader: Callable[[], Any],
        saver: Callable[[Any], None],
    ) -> Future[Any] | None:
        group = namespace if namespace in _EXECUTORS else "default"
        composite = (namespace, key)
        with runtime._CACHE_LOCK:  # noqa: SLF001
            current = runtime._INFLIGHT.get(composite)  # noqa: SLF001
            if current is not None and not current.done():
                return current
            active = sum(
                not future.done()
                for (
                    active_namespace,
                    _active_key,
                ), future in runtime._INFLIGHT.items()  # noqa: SLF001
                if (
                    active_namespace
                    if active_namespace in _EXECUTORS
                    else "default"
                )
                == group
            )
            # No hidden queue: stale data wins over waiting behind unrelated work.
            if active >= _POOL_SIZES[group]:
                return None
            future = _EXECUTORS[group].submit(loader)
            runtime._INFLIGHT[composite] = future  # noqa: SLF001

        def completed(done: Future[Any]) -> None:
            try:
                saver(done.result())
            except Exception:
                LOGGER.info(
                    "%s v8 refresh failed for %s",
                    namespace,
                    key,
                    exc_info=True,
                )
            finally:
                with runtime._CACHE_LOCK:  # noqa: SLF001
                    if runtime._INFLIGHT.get(composite) is done:  # noqa: SLF001
                        runtime._INFLIGHT.pop(composite, None)  # noqa: SLF001

        future.add_done_callback(completed)
        return future

    submit_once._osoli_priority_v8 = True  # type: ignore[attr-defined]
    runtime._submit_once = submit_once  # noqa: SLF001
    runtime._MAX_INFLIGHT = sum(_POOL_SIZES.values())  # noqa: SLF001
    runtime._HISTORY_BUDGET = min(  # noqa: SLF001
        runtime._HISTORY_BUDGET,  # noqa: SLF001
        _HISTORY_DEADLINE + 0.25,
    )
    runtime._QUOTE_BUDGET = min(  # noqa: SLF001
        runtime._QUOTE_BUDGET,  # noqa: SLF001
        _QUOTE_DEADLINE + 0.15,
    )


def _install_persistent_cache_hooks() -> None:
    import performance_runtime_v7 as runtime

    install_persistent_market_cache()
    original_history_saver = runtime._history_saver  # noqa: SLF001
    original_peek_history = runtime.peek_cached_history
    original_store_quote = runtime._store_quote  # noqa: SLF001
    original_peek_quote = runtime.peek_cached_quote

    def history_saver(key: Hashable, value: Any) -> None:
        original_history_saver(key, value)
        if isinstance(value, pd.DataFrame) and not value.empty:
            interval = (
                str(key[2])
                if isinstance(key, tuple) and len(key) > 2
                else "1d"
            )
            save_history(
                key,
                value,
                ttl_seconds=runtime._history_stale_ttl(interval),  # noqa: SLF001
            )

    def peek_history(
        symbol: str,
        *,
        period: str | None = None,
        interval: str = "1d",
        years: int | None = None,
        allow_stale: bool = True,
    ) -> pd.DataFrame:
        hot = original_peek_history(
            symbol,
            period=period,
            interval=interval,
            years=years,
            allow_stale=allow_stale,
        )
        if not hot.empty or not allow_stale:
            return hot
        key = runtime._history_key(  # noqa: SLF001
            symbol,
            period,
            interval,
            years,
        )
        loaded = load_history(
            key,
            max_stale_seconds=runtime._history_stale_ttl(interval),  # noqa: SLF001
        )
        if loaded is None:
            return pd.DataFrame()
        frame, age = loaded
        with runtime._CACHE_LOCK:  # noqa: SLF001
            runtime._HISTORY_CACHE[key] = (  # noqa: SLF001
                time.monotonic() - age,
                runtime._clone(frame),  # noqa: SLF001
            )
        return runtime._mark_stale(frame, True)  # noqa: SLF001

    def store_quote(symbol: str, payload: Any) -> None:
        original_store_quote(symbol, payload)
        if isinstance(payload, dict):
            save_quote(
                symbol,
                payload,
                ttl_seconds=max(runtime._quote_ttl() * 20.0, 3600.0),  # noqa: SLF001
            )

    def peek_quote(
        symbol: str,
        *,
        allow_stale: bool = True,
    ) -> dict[str, Any]:
        hot = original_peek_quote(symbol, allow_stale=allow_stale)
        if hot or not allow_stale:
            return hot
        maximum_age = max(runtime._quote_ttl() * 20.0, 3600.0)  # noqa: SLF001
        loaded = load_quote(symbol, max_stale_seconds=maximum_age)
        if loaded is None:
            return {}
        payload, age = loaded
        with runtime._CACHE_LOCK:  # noqa: SLF001
            runtime._QUOTE_CACHE[  # noqa: SLF001
                runtime._normalized_symbol(symbol)  # noqa: SLF001
            ] = (
                time.monotonic() - age,
                runtime._clone(payload),  # noqa: SLF001
            )
        return payload

    runtime._history_saver = history_saver  # noqa: SLF001
    runtime.peek_cached_history = peek_history
    runtime._store_quote = store_quote  # noqa: SLF001
    runtime.peek_cached_quote = peek_quote
    try:
        prune_expired()
    except Exception:
        LOGGER.debug("Persistent cache prune skipped", exc_info=True)


def _append_feature_pack(
    report: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    started = time.perf_counter()
    pack = build_sc_feature_pack(
        context.closed_history,
        context.interval,
    )
    report["sc_feature_pack"] = pack
    engine_meta = report.get("engine_meta")
    if not isinstance(engine_meta, dict):
        engine_meta = {}
    engine_meta["sc_feature_pack"] = {
        "version": SC_FEATURE_VERSION,
        "closed_candles_only": True,
        "fingerprint": context.fingerprint,
        "qualified": bool(pack.get("qualified")),
    }
    report["engine_meta"] = engine_meta
    features = report.get("features")
    if not isinstance(features, dict):
        features = {}
    if pack.get("ok"):
        features.update(
            {
                "sc_direction": int(pack.get("direction") or 0),
                "sc_event_direction": int(
                    pack.get("event_direction") or 0
                ),
                "sc_confidence": int(pack.get("confidence") or 0),
                "sc_qualified": int(bool(pack.get("qualified"))),
                "sc_range_compressed": int(
                    bool((pack.get("range") or {}).get("compressed"))
                ),
                "sc_channel_quality": int(
                    bool((pack.get("channel") or {}).get("quality"))
                ),
                "sc_participation": int(
                    bool((pack.get("candle") or {}).get("participation"))
                ),
            }
        )
    report["features"] = features
    report["sc_alignment"] = {
        "available": bool(pack.get("ok")),
        "qualified": bool(pack.get("qualified")),
        "direction": int(pack.get("direction") or 0),
        "event": pack.get("event_code"),
        "confidence": int(pack.get("confidence") or 0),
    }
    try:
        import performance_runtime_v7 as runtime

        runtime.record_phase(
            context.symbol,
            context.interval,
            "sc_feature_pack_ms",
            (time.perf_counter() - started) * 1000.0,
        )
    except Exception:
        LOGGER.debug("SC feature timing unavailable", exc_info=True)
    return report


def _install_report_hook() -> None:
    import analysis_context_v7 as context_module

    original = context_module.generate_with_context
    if getattr(original, "_osoli_sc_v8", False):
        return

    def generate_with_context(
        raw_generator: Any,
        symbol: str,
        timeframe: str,
        *,
        refresh: bool = False,
    ):
        report, context = original(
            raw_generator,
            symbol,
            timeframe,
            refresh=refresh,
        )
        if isinstance(report, dict) and not context.closed_history.empty:
            try:
                report = _append_feature_pack(report, context)
            except Exception:
                LOGGER.exception("SC feature pack failed")
                report["sc_feature_pack"] = {
                    "ok": False,
                    "version": SC_FEATURE_VERSION,
                    "reason": "feature_pack_error",
                }
        return report, context

    generate_with_context._osoli_sc_v8 = True  # type: ignore[attr-defined]
    context_module.generate_with_context = generate_with_context


def _install_bot_contract_health() -> None:
    try:
        from ai_engine_core import bot_bridge_v5 as bridge
    except Exception:
        return
    original = bridge.bot_health
    if getattr(original, "_osoli_contract_v8", False):
        return
    cache: dict[str, Any] = {"at": 0.0, "value": {}}
    lock = threading.RLock()

    def bot_health() -> dict[str, Any]:
        result = dict(original())
        base = bridge._base_url()  # noqa: SLF001
        headers = bridge._sync_headers()  # noqa: SLF001
        if not base or not headers or bridge.requests is None:
            result["integration_contract"] = {
                "ok": False,
                "reason": "sync_not_configured",
            }
            return result
        now = time.monotonic()
        with lock:
            if now - float(cache["at"]) <= 60.0 and cache["value"]:
                result["integration_contract"] = copy.deepcopy(
                    cache["value"]
                )
                return result
        try:
            response = bridge.requests.get(
                f"{base}/integrations/osoli/status",
                headers=headers,
                timeout=min(2.5, _QUOTE_DEADLINE),
            )
            body = response.json() if response.status_code == 200 else {}
            contract = {
                "ok": (
                    response.status_code == 200
                    and isinstance(body, dict)
                    and bool(body.get("ok"))
                ),
                "http_status": int(response.status_code),
                "contract": (
                    body.get("contract")
                    if isinstance(body, dict)
                    else None
                ),
                "mode": (
                    body.get("mode")
                    if isinstance(body, dict)
                    else None
                ),
                "same_plan_reuses_event_id": (
                    bool(body.get("same_plan_reuses_event_id"))
                    if isinstance(body, dict)
                    else False
                ),
            }
        except Exception:
            contract = {"ok": False, "reason": "unreachable"}
        with lock:
            cache["at"] = now
            cache["value"] = copy.deepcopy(contract)
        result["integration_contract"] = contract
        return result

    bot_health._osoli_contract_v8 = True  # type: ignore[attr-defined]
    bridge.bot_health = bot_health


def runtime_status() -> dict[str, Any]:
    with _PROVIDER_LOCK:
        providers = copy.deepcopy(_PROVIDER_STATS)
    return {
        "installed": _INSTALLED,
        "feature_version": SC_FEATURE_VERSION,
        "history_total_deadline_seconds": _HISTORY_DEADLINE,
        "quote_total_deadline_seconds": _QUOTE_DEADLINE,
        "pool_sizes": dict(_POOL_SIZES),
        "provider_stats": providers,
        "persistent_cache": True,
        "bot_contract_negotiation": True,
    }


def install_sc_runtime_v8() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        _install_priority_executors()
        _install_provider_deadlines()
        _install_persistent_cache_hooks()
        _install_report_hook()
        _install_bot_contract_health()
        _INSTALLED = True


__all__ = ["install_sc_runtime_v8", "runtime_status"]
