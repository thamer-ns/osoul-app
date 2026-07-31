"""Attach V17 live context after the final Osoli decision."""
from __future__ import annotations

import copy
import threading
from typing import Any

import live_market_report_v15 as previous
import live_market_runtime_v15 as runtime_v15
from live_market_runtime_v17 import (
    fetch_live_quote,
    install_live_market_runtime_v17,
    runtime_status,
)
from live_market_ui_v17 import install_live_market_ui_v17

_LOCK = threading.RLock()
_INSTALLED = False


def _public_quote(payload: dict[str, Any]) -> dict[str, Any]:
    base = previous._public_quote(payload)  # noqa: SLF001
    for name in (
        "source_spread_pct",
        "source_agreement_pct_semantics",
        "comparison_label",
        "closed_candle_price_preserved",
        "live_price_is_context_only",
    ):
        base[name] = copy.deepcopy(payload.get(name))
    base["fusion_version"] = "17.0"
    return base


def install_live_market_report_v17() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    with _LOCK:
        if _INSTALLED:
            return
        install_live_market_runtime_v17()
        # The V15 report module imported both functions by value. Replace those
        # globals before installing its final-decision wrapper.
        previous.fetch_live_quote = fetch_live_quote
        previous.runtime_status = runtime_status
        previous._public_quote = _public_quote  # noqa: SLF001
        runtime_v15.fetch_live_quote = fetch_live_quote
        previous.install_live_market_report_v15()
        install_live_market_ui_v17()
        try:
            import sc_runtime_v10

            old = sc_runtime_v10.runtime_status
            if not getattr(old, "_osoli_live_status_v17", False):

                def combined_status() -> dict[str, Any]:
                    status = dict(old())
                    status["live_market_runtime"] = runtime_status()
                    status["live_quote_changes_signal"] = False
                    status["live_quote_attached_after_final_decision"] = True
                    status["closed_candle_price_preserved"] = True
                    status["source_spread_not_agreement"] = True
                    return status

                combined_status._osoli_live_status_v17 = True  # type: ignore[attr-defined]
                sc_runtime_v10.runtime_status = combined_status
        except Exception:
            pass
        _INSTALLED = True


__all__ = ["install_live_market_report_v17"]
