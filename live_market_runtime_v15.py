"""Bounded live-quote consensus for Saudi instruments.

The technical engines continue to confirm structure, breakouts and stops from
completed candles.  This layer only refreshes the current market context and
never turns an intrabar quote into a confirmed signal.

Primary machine-readable sources:
- SAHMK when ``SAHMK_API_KEY`` is configured;
- Twelve Data when ``TWELVEDATA_API_KEY`` is configured;
- Yahoo chart as a delayed compatibility fallback.

Browser pages (Google Finance, Investing, Saudi Exchange website, TickerChart,
TradingView and Argaam) are deliberately not scraped in the decision path. They
are reference surfaces, not stable licensed APIs, and must never block Osoli.
"""
from __future__ import annotations

import copy
import logging
import math
import os
import statistics
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import quote as urlquote

try:
    import requests
except Exception:  # pragma: no cover - optional in constrained environments
    requests = None  # type: ignore[assignment]

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)
_INSTALL_LOCK = threading.RLock()
_CACHE_LOCK = threading.RLock()
_INSTALLED = False
_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="osoli-live-quote-v15")
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_INFLIGHT: dict[str, Future[dict[str, Any]]] = {}


def _number_env(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError, OverflowError):
        value = default
    if not math.isfinite(value):
        value = default
    return max(low, min(high, value))


_TOTAL_DEADLINE = _number_env("OSOUL_LIVE_QUOTE_DEADLINE_SECONDS", 2.35, 0.8, 5.0)
_SOURCE_TIMEOUT = _number_env("OSOUL_LIVE_QUOTE_SOURCE_TIMEOUT_SECONDS", 1.55, 0.4, 3.0)
_CACHE_TTL = _number_env("OSOUL_LIVE_QUOTE_TTL_SECONDS", 20.0, 5.0, 120.0)
_MAX_CONTEXT_AGE = _number_env("OSOUL_LIVE_QUOTE_MAX_AGE_SECONDS", 180.0, 30.0, 1800.0)
_AGREEMENT_PCT = _number_env("OSOUL_LIVE_QUOTE_AGREEMENT_PCT", 0.80, 0.10, 5.0)

_SESSION = requests.Session() if requests is not None else None
if _SESSION is not None:
    _SESSION.headers.update(
        {
            "User-Agent": "Osoli/15.0 live-market-context",
            "Accept": "application/json,text/plain,*/*",
        }
    )


def _secret(name: str) -> str:
    if st is not None:
        try:
            value = st.secrets.get(name, "")  # type: ignore[union-attr]
            if value:
                return str(value).strip()
        except Exception:
            LOGGER.debug("Streamlit secret lookup failed for %s", name, exc_info=True)
    return str(os.getenv(name, "") or "").strip()


def _finite_positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _epoch(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        number = math.nan
    if math.isfinite(number) and number > 0:
        return int(number / 1000 if number > 10_000_000_000 else number)
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.astimezone(timezone.utc).timestamp())


def _saudi_symbol(symbol: str) -> tuple[str, str] | None:
    raw = str(symbol or "").strip().upper()
    for prefix in ("TADAWUL:", "XSAU:"):
        raw = raw.removeprefix(prefix)
    if raw in {"TASI", "^TASI", "^TASI.SR", "TASI.SR"}:
        return "TASI", "^TASI.SR"
    raw = raw.replace("SR.", "").replace(".SR", "")
    if raw.isdigit() and 4 <= len(raw) <= 6:
        return raw, f"{raw}.SR"
    return None


def _request_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[Any, str, int]:
    if _SESSION is None:
        return None, "requests_unavailable", 0
    started = time.perf_counter()
    connect = min(0.55, max(0.20, _SOURCE_TIMEOUT * 0.30))
    read = max(0.20, _SOURCE_TIMEOUT - connect)
    try:
        response = _SESSION.get(
            url,
            params=params or {},
            headers=headers or {},
            timeout=(round(connect, 3), round(read, 3)),
            allow_redirects=True,
        )
        elapsed = round((time.perf_counter() - started) * 1000)
        if response.status_code != 200:
            return None, f"http_{int(response.status_code)}", elapsed
        try:
            payload = response.json()
        except ValueError:
            return None, "invalid_json", elapsed
        return payload, "", elapsed
    except Exception as exc:
        elapsed = round((time.perf_counter() - started) * 1000)
        return None, type(exc).__name__.lower(), elapsed


def _observation(
    *,
    source: str,
    price: Any,
    previous: Any = None,
    timestamp: Any = None,
    volume: Any = None,
    year_high: Any = None,
    year_low: Any = None,
    delayed: bool,
    priority: int,
    latency_ms: int,
) -> dict[str, Any]:
    live = _finite_positive(price)
    if live is None:
        return {}
    return {
        "source": source,
        "price": live,
        "prev_close": _finite_positive(previous),
        "timestamp": _epoch(timestamp),
        "volume": _finite_positive(volume),
        "year_high": _finite_positive(year_high),
        "year_low": _finite_positive(year_low),
        "delayed": bool(delayed),
        "priority": int(priority),
        "latency_ms": max(0, int(latency_ms)),
    }


def _quote_sahmk(code: str, _yahoo_symbol: str) -> tuple[dict[str, Any], dict[str, Any]]:
    key = _secret("SAHMK_API_KEY")
    if not key:
        return {}, {"provider": "sahmk", "ok": False, "reason": "not_configured"}
    base = str(
        _secret("SAHMK_API_BASE_URL")
        or "https://app.sahmk.sa/api/v1"
    ).rstrip("/")
    payload, reason, elapsed = _request_json(
        f"{base}/quote/{urlquote(code, safe='')}/",
        headers={"X-API-Key": key},
    )
    row: Any = payload
    if isinstance(payload, dict):
        for name in ("data", "quote", "result"):
            if isinstance(payload.get(name), dict):
                row = payload[name]
                break
    row = row if isinstance(row, dict) else {}
    observation = _observation(
        source="sahmk",
        price=row.get("price") or row.get("last") or row.get("last_price") or row.get("close"),
        previous=row.get("previous_close") or row.get("prev_close") or row.get("previousClose"),
        timestamp=row.get("timestamp") or row.get("updated_at") or row.get("market_time"),
        volume=row.get("volume") or row.get("traded_volume"),
        year_high=row.get("year_high") or row.get("fifty_two_week_high"),
        year_low=row.get("year_low") or row.get("fifty_two_week_low"),
        delayed=bool(row.get("is_delayed", False)),
        priority=0,
        latency_ms=elapsed,
    )
    return observation, {
        "provider": "sahmk",
        "ok": bool(observation),
        "reason": "" if observation else reason or "invalid_or_missing_price",
        "elapsed_ms": elapsed,
    }


def _quote_twelvedata(code: str, _yahoo_symbol: str) -> tuple[dict[str, Any], dict[str, Any]]:
    key = _secret("TWELVEDATA_API_KEY")
    if not key:
        return {}, {"provider": "twelvedata", "ok": False, "reason": "not_configured"}
    payload, reason, elapsed = _request_json(
        "https://api.twelvedata.com/quote",
        params={
            "symbol": code,
            "exchange": "XSAU",
            "apikey": key,
            "format": "JSON",
        },
    )
    row = payload if isinstance(payload, dict) else {}
    provider_error = str(row.get("status") or "").lower() == "error"
    observation = {} if provider_error else _observation(
        source="twelvedata",
        price=row.get("close") or row.get("price"),
        previous=row.get("previous_close") or row.get("prev_close"),
        timestamp=row.get("timestamp") or row.get("datetime"),
        volume=row.get("volume"),
        year_high=row.get("fifty_two_week", {}).get("high")
        if isinstance(row.get("fifty_two_week"), dict)
        else row.get("fifty_two_week_high"),
        year_low=row.get("fifty_two_week", {}).get("low")
        if isinstance(row.get("fifty_two_week"), dict)
        else row.get("fifty_two_week_low"),
        delayed=False,
        priority=1,
        latency_ms=elapsed,
    )
    return observation, {
        "provider": "twelvedata",
        "ok": bool(observation),
        "reason": "" if observation else reason or str(row.get("message") or "invalid_or_missing_price")[:80],
        "elapsed_ms": elapsed,
    }


def _quote_yahoo(_code: str, yahoo_symbol: str) -> tuple[dict[str, Any], dict[str, Any]]:
    payload, reason, elapsed = _request_json(
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urlquote(yahoo_symbol, safe=".^=-"),
        params={"interval": "1m", "range": "1d", "includePrePost": "false"},
    )
    chart = payload.get("chart") if isinstance(payload, dict) else None
    result = chart.get("result") if isinstance(chart, dict) else None
    item = result[0] if isinstance(result, list) and result else {}
    meta = item.get("meta") if isinstance(item, dict) else {}
    meta = meta if isinstance(meta, dict) else {}
    observation = _observation(
        source="yahoo",
        price=meta.get("regularMarketPrice") or meta.get("previousClose"),
        previous=meta.get("chartPreviousClose") or meta.get("previousClose"),
        timestamp=meta.get("regularMarketTime"),
        volume=meta.get("regularMarketVolume"),
        year_high=meta.get("fiftyTwoWeekHigh"),
        year_low=meta.get("fiftyTwoWeekLow"),
        delayed=True,
        priority=3,
        latency_ms=elapsed,
    )
    return observation, {
        "provider": "yahoo",
        "ok": bool(observation),
        "reason": "" if observation else reason or "invalid_or_missing_price",
        "elapsed_ms": elapsed,
    }


def _choose_consensus(
    symbol: str,
    observations: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    valid = [item for item in observations if _finite_positive(item.get("price"))]
    if not valid:
        return {}
    valid.sort(key=lambda item: (int(item.get("priority", 99)), str(item.get("source"))))
    prices = [float(item["price"]) for item in valid]
    median_price = float(statistics.median(prices))
    spread_pct = (
        (max(prices) - min(prices)) / median_price * 100.0
        if len(prices) > 1 and median_price > 0
        else 0.0
    )
    conflict = len(prices) > 1 and spread_pct > _AGREEMENT_PCT

    if conflict and len(valid) >= 3:
        chosen = min(
            valid,
            key=lambda item: (
                abs(float(item["price"]) - median_price) / median_price,
                int(item.get("priority", 99)),
            ),
        )
    else:
        chosen = valid[0]

    timestamp = chosen.get("timestamp")
    now_epoch = int(time.time())
    age_seconds = max(0, now_epoch - int(timestamp)) if timestamp else None
    stale = age_seconds is not None and age_seconds > _MAX_CONTEXT_AGE
    if conflict:
        confidence = "low"
    elif len(valid) >= 2 and spread_pct <= min(0.50, _AGREEMENT_PCT):
        confidence = "high" if not chosen.get("delayed") else "medium"
    elif chosen.get("source") in {"sahmk", "twelvedata"}:
        confidence = "medium"
    else:
        confidence = "low"

    previous = chosen.get("prev_close")
    price = float(chosen["price"])
    change = ((price - previous) / previous * 100.0) if previous else None
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "symbol": symbol,
        "resolved_symbol": symbol,
        "price": price,
        "prev_close": previous,
        "previous_close": previous,
        "change_pct": round(change, 4) if change is not None else None,
        "change_percent": round(change, 4) if change is not None else None,
        "change_available": change is not None,
        "year_high": chosen.get("year_high"),
        "year_low": chosen.get("year_low"),
        "volume": chosen.get("volume"),
        "source": str(chosen.get("source") or ""),
        "quote_timestamp": timestamp,
        "quote_age_seconds": age_seconds,
        "fetched_at": fetched_at,
        "is_stale": bool(stale),
        "is_delayed": bool(chosen.get("delayed")),
        "price_confidence": confidence,
        "price_conflict": bool(conflict),
        "source_count": len(valid),
        "source_agreement_pct": round(spread_pct, 4),
        "sources": [str(item.get("source") or "") for item in valid],
        "provider_attempts": attempts,
        "decision_use": "live_context_only_closed_candle_confirmation",
        "browser_reference_sources": [
            "saudi_exchange_delayed_website",
            "google_finance",
            "investing",
            "tickerchart",
            "tradingview",
            "argaam",
        ],
        "browser_sources_used_for_decision": False,
        "fusion_version": "15.0",
        "total_deadline_seconds": _TOTAL_DEADLINE,
    }


def _load_saudi_quote(symbol: str) -> dict[str, Any]:
    resolved = _saudi_symbol(symbol)
    if resolved is None:
        return {}
    code, yahoo_symbol = resolved
    tasks: tuple[Callable[[str, str], tuple[dict[str, Any], dict[str, Any]]], ...] = (
        _quote_sahmk,
        _quote_twelvedata,
        _quote_yahoo,
    )
    future_map = {
        _EXECUTOR.submit(loader, code, yahoo_symbol): loader.__name__
        for loader in tasks
    }
    done, pending = wait(tuple(future_map), timeout=_TOTAL_DEADLINE)
    for future in pending:
        future.cancel()
    observations: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    for future in done:
        try:
            observation, attempt = future.result()
        except Exception as exc:
            attempts.append(
                {
                    "provider": future_map[future].removeprefix("_quote_"),
                    "ok": False,
                    "reason": type(exc).__name__.lower(),
                }
            )
            continue
        attempts.append(dict(attempt))
        if observation:
            observations.append(dict(observation))
    for future in pending:
        attempts.append(
            {
                "provider": future_map[future].removeprefix("_quote_"),
                "ok": False,
                "reason": "total_deadline_exceeded",
            }
        )
    attempts.sort(key=lambda row: str(row.get("provider") or ""))
    return _choose_consensus(yahoo_symbol, observations, attempts)


def fetch_live_quote(
    symbol: str,
    *,
    fallback: Callable[[str], tuple[dict[str, Any], list[dict[str, Any]]]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return one bounded live context quote and preserve the legacy tuple API."""
    normalized = str(symbol or "").strip().upper()
    if _saudi_symbol(normalized) is None:
        return fallback(normalized) if callable(fallback) else ({}, [])

    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(normalized)
        inflight = _INFLIGHT.get(normalized)
    if cached and now - cached[0] <= _CACHE_TTL:
        payload = copy.deepcopy(cached[1])
        payload["cache_mode"] = "fresh"
        return payload, list(payload.get("provider_attempts") or [])

    if inflight is None or inflight.done():
        future = _EXECUTOR.submit(_load_saudi_quote, normalized)
        with _CACHE_LOCK:
            _INFLIGHT[normalized] = future
        inflight = future
    try:
        payload = inflight.result(timeout=_TOTAL_DEADLINE + 0.10)
    except Exception:
        payload = {}
    finally:
        if inflight.done():
            with _CACHE_LOCK:
                if _INFLIGHT.get(normalized) is inflight:
                    _INFLIGHT.pop(normalized, None)

    if payload:
        with _CACHE_LOCK:
            _CACHE[normalized] = (time.monotonic(), copy.deepcopy(payload))
        payload["cache_mode"] = "network"
        return payload, list(payload.get("provider_attempts") or [])

    if cached:
        stale = copy.deepcopy(cached[1])
        stale["is_stale"] = True
        stale["cache_mode"] = "stale_while_revalidate"
        return stale, list(stale.get("provider_attempts") or [])
    return fallback(normalized) if callable(fallback) else ({}, [])


def runtime_status() -> dict[str, Any]:
    return {
        "runtime_version": "15.0",
        "scope": "saudi_live_quote_context",
        "sahmk_configured": len(_secret("SAHMK_API_KEY")) >= 16,
        "twelvedata_configured": bool(_secret("TWELVEDATA_API_KEY")),
        "yahoo_delayed_fallback": True,
        "quote_ttl_seconds": _CACHE_TTL,
        "total_deadline_seconds": _TOTAL_DEADLINE,
        "agreement_threshold_pct": _AGREEMENT_PCT,
        "browser_sources_used_for_decision": False,
        "closed_candle_confirmation_unchanged": True,
    }


def install_live_market_runtime_v15() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        import market_data
        import market_data_router_v5 as router
        import market_providers_v5 as providers
        import performance_runtime_v7 as performance

        original = router.fetch_quote

        def quote_router(symbol: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
            return fetch_live_quote(symbol, fallback=original)

        quote_router._osoli_live_market_v15 = True  # type: ignore[attr-defined]
        router.fetch_quote = quote_router
        providers.fetch_quote = quote_router

        def quote_ttl() -> float:
            return _CACHE_TTL

        performance._quote_ttl = quote_ttl  # noqa: SLF001
        market_data.live_quote_status_v15 = runtime_status
        market_data.fetch_live_quote_v15 = quote_router
        _INSTALLED = True


__all__ = [
    "fetch_live_quote",
    "install_live_market_runtime_v15",
    "runtime_status",
]
