"""Attach live Saudi quote metadata after the final closed-candle decision."""
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
        "freshness_status",
        "future_timestamp_rejected",
        "is_stale",
        "delay_status",
        "is_delayed",
        "price_confidence",
        "price_conflict",
        "source_count",
        "source_agreement_pct",
        "sources",
        "cache_mode",
        "cache_age_seconds",
        "decision_use",
        "browser_sources_used_for_decision",
        "fusion_version",
    )
    return {name: copy.deepcopy(payload.get(name)) for name in names}


def _attach_live_context(
    report: dict[str, Any],
    *,
    symbol: str,
) -> dict[str, Any]:
    if _saudi_symbol(symbol) is None:
        return report
    try:
        quote, _attempts = fetch_live_quote(symbol)
    except Exception:
        LOGGER.info("Live quote context failed for %s", symbol, exc_info=True)
        quote = {}
    if not quote:
        return report

    public = _public_quote(quote)
    report["live_quote_context"] = public
    # These fields are appended after the decision engine has completed.  They
    # are presentation/diagnostic facts and cannot influence direction or plan.
    features = report.get("features")
    if not isinstance(features, dict):
        features = {}
    features.update(
        {
            "live_price": public.get("price"),
            "live_price_confidence": public.get("price_confidence"),
            "live_price_conflict": int(bool(public.get("price_conflict"))),
            "live_price_delayed": int(public.get("delay_status") == "delayed"),
            "live_price_age_seconds": public.get("quote_age_seconds"),
        }
    )
    report["features"] = features
    engine_meta = report.get("engine_meta")
    if not isinstance(engine_meta, dict):
        engine_meta = {}
    engine_meta["live_quote"] = {
        "runtime": "16.0",
        "source": public.get("source"),
        "confidence": public.get("price_confidence"),
        "delay_status": public.get("delay_status"),
        "freshness_status": public.get("freshness_status"),
        "changes_signal": False,
        "attached_after_final_decision": True,
        "closed_candle_confirmation": True,
    }
    report["engine_meta"] = engine_meta
    return report


def install_live_market_report_v15() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # Patch the final policy rather than analysis_context.  The earlier V15
    # wrapper attached live fields before qualification; moving this boundary
    # makes the non-influence guarantee structural, not merely conventional.
    from ai_engine_core import decision_policy_v6 as policy

    original = policy.enrich_report
    if getattr(original, "_osoli_live_market_report_v16", False):
        _INSTALLED = True
        return

    def enrich_report(
        report: Any,
        *,
        symbol: str = "",
        timeframe: str = "1D",
    ) -> dict[str, Any]:
        final = original(report, symbol=symbol, timeframe=timeframe)
        if not isinstance(final, dict):
            return final
        return _attach_live_context(final, symbol=symbol)

    enrich_report._osoli_live_market_report_v16 = True  # type: ignore[attr-defined]
    policy.enrich_report = enrich_report

    try:
        import sc_runtime_v10

        previous_status = sc_runtime_v10.runtime_status
        if not getattr(previous_status, "_osoli_live_status_v16", False):

            def combined_status() -> dict[str, Any]:
                status = dict(previous_status())
                status["live_market_runtime"] = runtime_status()
                status["live_quote_changes_signal"] = False
                status["live_quote_attached_after_final_decision"] = True
                return status

            combined_status._osoli_live_status_v16 = True  # type: ignore[attr-defined]
            sc_runtime_v10.runtime_status = combined_status
    except Exception:
        LOGGER.debug("SC runtime status extension skipped", exc_info=True)
    _INSTALLED = True


__all__ = ["install_live_market_report_v15"]
