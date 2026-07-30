"""Attach live Saudi quote metadata after the closed-candle report is built."""
from __future__ import annotations

import copy
import logging
from typing import Any

from live_market_runtime_v15 import _saudi_symbol, fetch_live_quote, runtime_status

LOGGER = logging.getLogger(__name__)
_INSTALLED = False


def _public_quote(payload: dict[str, Any]) -> dict[str, Any]:
    """Expose decision-safe metadata only; provider attempts never contain keys."""
    names = (
        "price",
        "prev_close",
        "change_pct",
        "source",
        "quote_timestamp",
        "quote_age_seconds",
        "fetched_at",
        "is_stale",
        "is_delayed",
        "price_confidence",
        "price_conflict",
        "source_count",
        "source_agreement_pct",
        "sources",
        "decision_use",
        "browser_sources_used_for_decision",
        "fusion_version",
    )
    return {name: copy.deepcopy(payload.get(name)) for name in names}


def install_live_market_report_v15() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    import analysis_context_v7 as context_module

    original = context_module.generate_with_context
    if getattr(original, "_osoli_live_market_report_v15", False):
        _INSTALLED = True
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
        if not isinstance(report, dict) or _saudi_symbol(symbol) is None:
            return report, context
        try:
            quote, _attempts = fetch_live_quote(symbol)
        except Exception:
            LOGGER.info("Live quote context failed for %s", symbol, exc_info=True)
            quote = {}
        if not quote:
            return report, context

        public = _public_quote(quote)
        report["live_quote_context"] = public
        features = report.get("features")
        if not isinstance(features, dict):
            features = {}
        features.update(
            {
                "live_price": public.get("price"),
                "live_price_confidence": public.get("price_confidence"),
                "live_price_conflict": int(bool(public.get("price_conflict"))),
                "live_price_delayed": int(bool(public.get("is_delayed"))),
                "live_price_age_seconds": public.get("quote_age_seconds"),
            }
        )
        report["features"] = features
        engine_meta = report.get("engine_meta")
        if not isinstance(engine_meta, dict):
            engine_meta = {}
        engine_meta["live_quote"] = {
            "runtime": "15.0",
            "source": public.get("source"),
            "confidence": public.get("price_confidence"),
            "changes_signal": False,
            "closed_candle_confirmation": True,
        }
        report["engine_meta"] = engine_meta
        return report, context

    generate_with_context._osoli_live_market_report_v15 = True  # type: ignore[attr-defined]
    context_module.generate_with_context = generate_with_context

    try:
        import sc_runtime_v10

        previous_status = sc_runtime_v10.runtime_status

        def combined_status() -> dict[str, Any]:
            status = dict(previous_status())
            status["live_market_runtime"] = runtime_status()
            status["live_quote_changes_signal"] = False
            return status

        sc_runtime_v10.runtime_status = combined_status
    except Exception:
        LOGGER.debug("SC runtime status extension skipped", exc_info=True)
    _INSTALLED = True


__all__ = ["install_live_market_report_v15"]
