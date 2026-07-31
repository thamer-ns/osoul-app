"""Osoli V17 live-quote semantics: spread is not source agreement."""
from __future__ import annotations

import copy
import math
import threading
from typing import Any, Callable

import live_market_runtime_v15 as previous

_LOCK = threading.RLock()
_INSTALLED = False


def _finite_nonnegative(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _normalize(payload: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    spread = _finite_nonnegative(
        result.get("source_spread_pct", result.get("source_agreement_pct"))
    )
    try:
        source_count = max(0, int(result.get("source_count") or 0))
    except (TypeError, ValueError, OverflowError):
        source_count = 0
    result["source_spread_pct"] = spread
    # Preserve the old key for readers that have not migrated, while exposing
    # its exact semantics so nobody interprets 0% from one source as agreement.
    result["source_agreement_pct"] = spread
    result["source_agreement_pct_semantics"] = "spread_not_agreement"
    result["comparison_label"] = (
        "مصدر واحد — لا يمكن قياس اتفاق المصادر"
        if source_count <= 1
        else f"فارق المصادر {spread:.2f}%"
        if spread is not None
        else f"{source_count} مصادر — تعذر حساب الفارق"
    )
    result["closed_candle_price_preserved"] = True
    result["live_price_is_context_only"] = True
    result["fusion_version"] = "17.0"
    return result


def fetch_live_quote(
    symbol: str,
    *,
    fallback: Callable[[str], tuple[dict[str, Any], list[dict[str, Any]]]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload, attempts = previous.fetch_live_quote(symbol, fallback=fallback)
    return (_normalize(payload) if payload else {}, list(attempts))


def runtime_status() -> dict[str, Any]:
    status = dict(previous.runtime_status())
    status.update(
        {
            "runtime_version": "17.0",
            "source_spread_label_correct": True,
            "single_source_agreement_not_claimed": True,
            "closed_candle_price_preserved": True,
            "live_price_is_context_only": True,
        }
    )
    return status


def install_live_market_runtime_v17() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    with _LOCK:
        if _INSTALLED:
            return
        previous.install_live_market_runtime_v15()
        current = previous.fetch_live_quote
        if not getattr(current, "_osoli_live_market_v17", False):

            def wrapped(
                symbol: str,
                *,
                fallback: Callable[
                    [str], tuple[dict[str, Any], list[dict[str, Any]]]
                ]
                | None = None,
            ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
                payload, attempts = current(symbol, fallback=fallback)
                return (_normalize(payload) if payload else {}, list(attempts))

            wrapped._osoli_live_market_v17 = True  # type: ignore[attr-defined]
            previous.fetch_live_quote = wrapped
        import market_data

        market_data.live_quote_status_v17 = runtime_status
        market_data.fetch_live_quote_v17 = fetch_live_quote
        _INSTALLED = True


__all__ = [
    "fetch_live_quote",
    "install_live_market_runtime_v17",
    "runtime_status",
]
