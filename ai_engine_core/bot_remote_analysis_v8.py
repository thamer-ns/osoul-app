"""On-demand authenticated analysis call from Osoli to the market bot."""
from __future__ import annotations

import logging
from typing import Any

from ai_engine_core import bot_bridge_v5 as bridge
from bot_contract_runtime_v10 import (
    EXPECTED_CONTRACT,
    EXPECTED_FEATURE_VERSION,
    EXPECTED_INDICATOR_CONTRACT,
    EXPECTED_RUNTIME_VERSION,
)

LOGGER = logging.getLogger(__name__)
_FRAME_ALIASES = {
    "60m": "1h",
    "60min": "1h",
    "240m": "4h",
    "1wk": "1w",
    "week": "1w",
    "weekly": "1w",
    "month": "1mo",
    "monthly": "1mo",
}


def _canonical_frame(value: str) -> str:
    raw = str(value or "1d").strip().lower()
    return _FRAME_ALIASES.get(raw, raw)


def _runtime_is_compatible(runtime: dict[str, Any]) -> str | None:
    if runtime.get("installed") is not True:
        return "runtime_not_installed"
    if str(runtime.get("runtime_version") or "") != EXPECTED_RUNTIME_VERSION:
        return "runtime_version_mismatch"
    if str(runtime.get("feature_version") or "") != EXPECTED_FEATURE_VERSION:
        return "feature_version_mismatch"
    if str(runtime.get("indicator_contract") or "") != EXPECTED_INDICATOR_CONTRACT:
        return "indicator_contract_mismatch"
    if runtime.get("failure_single_flight") is not True:
        return "failure_single_flight_missing"
    if runtime.get("stale_fallback_age_bounded") is not True:
        return "stale_fallback_unbounded"
    if runtime.get("live_quote_overlay") is not True:
        return "live_quote_overlay_missing"
    if runtime.get("live_quote_changes_signal") is not False:
        return "live_quote_may_change_signal"
    if runtime.get("closed_candle_confirmation_unchanged") is not True:
        return "closed_candle_guard_missing"
    live = (
        runtime.get("live_quote_context")
        if isinstance(runtime.get("live_quote_context"), dict)
        else {}
    )
    if live.get("stale_fallback_age_bounded") is not True:
        return "live_quote_stale_unbounded"
    if live.get("delay_status_is_tristate") is not True:
        return "live_quote_delay_unknown_unsafe"
    return None


def request_bot_analysis(symbol: str, timeframe: str) -> dict[str, Any]:
    base = bridge._base_url()  # noqa: SLF001
    headers = bridge._sync_headers()  # noqa: SLF001
    if not base or not headers or bridge.requests is None:
        return {"ok": False, "reason": "sync_not_configured"}
    requested_frame = _canonical_frame(timeframe)
    try:
        response = bridge.requests.post(
            f"{base}/integrations/osoli/analysis",
            headers=headers,
            json={
                "symbol": str(symbol or "").strip().upper(),
                "frame": requested_frame,
            },
            timeout=(1.5, 10.0),
        )
        if response.status_code != 200:
            reason = {
                503: "market_data_unavailable",
                504: "analysis_deadline_exceeded",
            }.get(response.status_code, f"http_{response.status_code}")
            return {"ok": False, "reason": reason}
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("ok"):
            return {"ok": False, "reason": "invalid_response"}
        if str(payload.get("contract") or "") != EXPECTED_CONTRACT:
            return {"ok": False, "reason": "contract_mismatch"}
        if payload.get("tenant_ids_received") is not False:
            return {"ok": False, "reason": "unsafe_contract_flags"}
        frame = payload.get("frame")
        if not isinstance(frame, dict):
            return {"ok": False, "reason": "invalid_frame_payload"}
        if _canonical_frame(str(frame.get("frame_key") or "")) != requested_frame:
            return {"ok": False, "reason": "frame_mismatch"}
        runtime = payload.get("runtime")
        if not isinstance(runtime, dict):
            return {"ok": False, "reason": "runtime_not_installed"}
        incompatibility = _runtime_is_compatible(runtime)
        if incompatibility:
            return {"ok": False, "reason": incompatibility}
        live_context = payload.get("live_quote_context")
        if not isinstance(live_context, dict):
            return {"ok": False, "reason": "live_quote_context_missing"}
        if live_context.get("changes_signal") is not False:
            return {"ok": False, "reason": "live_quote_may_change_signal"}
        if live_context.get("closed_candle_confirmation") is not True:
            return {"ok": False, "reason": "closed_candle_guard_missing"}
        return payload
    except ValueError:
        LOGGER.info("Remote bot analysis returned invalid JSON", exc_info=True)
        return {"ok": False, "reason": "invalid_response"}
    except Exception:
        LOGGER.info("Remote bot analysis failed", exc_info=True)
        return {"ok": False, "reason": "unreachable"}


__all__ = ["request_bot_analysis"]
