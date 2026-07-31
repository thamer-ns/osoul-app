"""Authoritative low-latency discovery of the linked bot runtime contract."""
from __future__ import annotations

import copy
import logging
import threading
import time
from typing import Any

from ai_engine_core import bot_bridge_v5 as bridge

LOGGER = logging.getLogger(__name__)
EXPECTED_CONTRACT = "SC-V92.5-v1-plan-isolation-v61"
EXPECTED_RUNTIME_VERSION = "61.0"
EXPECTED_FEATURE_VERSION = "58.0"
EXPECTED_INDICATOR_CONTRACT = "SC-V92.5/SC-FXM-V16"
_LOCK = threading.RLock()
_INSTALLED = False
_CACHE: dict[str, Any] = {"at": 0.0, "value": {}}
_CACHE_SECONDS = 60.0


def _invalid(reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "reason": reason,
        "contract": None,
        "remote_analysis": False,
        **extra,
    }


def _probe_runtime() -> dict[str, Any]:
    base = bridge._base_url()  # noqa: SLF001
    headers = bridge._sync_headers()  # noqa: SLF001
    if not base or not headers or bridge.requests is None:
        return _invalid("sync_not_configured")
    try:
        response = bridge.requests.get(
            f"{base}/integrations/osoli/runtime",
            headers=headers,
            timeout=(1.2, 3.0),
        )
    except Exception:
        LOGGER.info("Bot runtime discovery failed", exc_info=True)
        return _invalid("unreachable")
    if response.status_code != 200:
        return _invalid(
            f"http_{response.status_code}",
            http_status=int(response.status_code),
        )
    try:
        body = response.json()
    except ValueError:
        return _invalid("invalid_response", http_status=200)
    if not isinstance(body, dict) or not body.get("ok"):
        return _invalid("invalid_response", http_status=200)

    contract = str(body.get("contract") or "")
    runtime = body.get("runtime") if isinstance(body.get("runtime"), dict) else {}
    live = (
        runtime.get("live_quote_context")
        if isinstance(runtime.get("live_quote_context"), dict)
        else {}
    )
    remote_analysis = body.get("remote_analysis") is True
    tenant_safe = body.get("tenant_ids_received") is False
    token_safe = body.get("token_in_url") is False
    installed = runtime.get("installed") is True
    runtime_version = str(runtime.get("runtime_version") or "")
    feature_version = str(runtime.get("feature_version") or "")
    indicator_contract = str(runtime.get("indicator_contract") or "")
    failure_single_flight = runtime.get("failure_single_flight") is True
    stale_bounded = runtime.get("stale_fallback_age_bounded") is True
    live_overlay = runtime.get("live_quote_overlay") is True
    live_signal_safe = runtime.get("live_quote_changes_signal") is False
    closed_candle_safe = (
        runtime.get("closed_candle_confirmation_unchanged") is True
        and live.get("closed_candle_confirmation_unchanged") is True
    )
    closed_price_safe = (
        runtime.get("closed_price_preserved") is True
        and live.get("closed_price_preserved") is True
        and live.get("live_price_persisted_as_analysis_price") is False
    )
    live_stale_bounded = live.get("stale_fallback_age_bounded") is True
    delay_tristate = live.get("delay_status_is_tristate") is True
    spread_semantics = live.get("source_spread_label_correct") is True

    checks = {
        "contract": contract == EXPECTED_CONTRACT,
        "remote_analysis": remote_analysis,
        "tenant_safe": tenant_safe,
        "token_safe": token_safe,
        "runtime_installed": installed,
        "runtime_version": runtime_version == EXPECTED_RUNTIME_VERSION,
        "feature_version": feature_version == EXPECTED_FEATURE_VERSION,
        "indicator_contract": indicator_contract == EXPECTED_INDICATOR_CONTRACT,
        "failure_single_flight": failure_single_flight,
        "stale_fallback_age_bounded": stale_bounded,
        "live_quote_overlay": live_overlay,
        "live_quote_signal_safe": live_signal_safe,
        "closed_candle_confirmation": closed_candle_safe,
        "closed_price_preserved": closed_price_safe,
        "live_quote_stale_bounded": live_stale_bounded,
        "delay_status_tristate": delay_tristate,
        "source_spread_semantics": spread_semantics,
    }
    reason_map = {
        "contract": "contract_mismatch",
        "remote_analysis": "remote_analysis_disabled",
        "tenant_safe": "unsafe_contract_flags",
        "token_safe": "unsafe_contract_flags",
        "runtime_installed": "runtime_not_installed",
        "runtime_version": "runtime_version_mismatch",
        "feature_version": "feature_version_mismatch",
        "indicator_contract": "indicator_contract_mismatch",
        "failure_single_flight": "failure_single_flight_missing",
        "stale_fallback_age_bounded": "stale_fallback_unbounded",
        "live_quote_overlay": "live_quote_overlay_missing",
        "live_quote_signal_safe": "live_quote_may_change_signal",
        "closed_candle_confirmation": "closed_candle_guard_missing",
        "closed_price_preserved": "closed_price_may_be_overwritten",
        "live_quote_stale_bounded": "live_quote_stale_unbounded",
        "delay_status_tristate": "live_quote_delay_unknown_unsafe",
        "source_spread_semantics": "source_comparison_semantics_unsafe",
    }
    failed = next((name for name, passed in checks.items() if not passed), None)
    reason = reason_map.get(failed) if failed else None
    return {
        "ok": failed is None,
        "reason": reason,
        "http_status": 200,
        "contract": contract or None,
        "expected_contract": EXPECTED_CONTRACT,
        "mode": body.get("mode"),
        "remote_analysis": remote_analysis,
        "same_plan_reuses_event_id": bool(body.get("same_plan_reuses_event_id")),
        "tenant_ids_received": body.get("tenant_ids_received"),
        "token_in_url": body.get("token_in_url"),
        "supported_frames": body.get("supported_frames"),
        "app_version": body.get("app_version"),
        "analysis_deadline_seconds": body.get("analysis_deadline_seconds"),
        "feature_version": feature_version or None,
        "runtime_version": runtime_version or None,
        "runtime_installed": installed,
        "indicator_contract": indicator_contract or None,
        "failure_single_flight": failure_single_flight,
        "stale_fallback_age_bounded": stale_bounded,
        "closed_price_preserved": closed_price_safe,
        "live_quote_context": copy.deepcopy(live),
        "capability_checks": checks,
        "endpoint": "/integrations/osoli/runtime",
    }


def bot_health() -> dict[str, Any]:
    now = time.monotonic()
    with _LOCK:
        if now - float(_CACHE["at"]) <= _CACHE_SECONDS and _CACHE["value"]:
            return copy.deepcopy(_CACHE["value"])
    contract = _probe_runtime()
    result = {
        "ok": bool(contract.get("ok")),
        "reason": contract.get("reason"),
        "version": contract.get("app_version"),
        "supported_frames": contract.get("supported_frames"),
        "school_consensus": "enabled" if contract.get("feature_version") else None,
        "osoli_sync": "enabled" if contract.get("ok") else "unavailable",
        "integration_contract": contract,
    }
    with _LOCK:
        _CACHE["at"] = now
        _CACHE["value"] = copy.deepcopy(result)
    return result


def runtime_status() -> dict[str, Any]:
    with _LOCK:
        return {
            "installed": _INSTALLED,
            "expected_contract": EXPECTED_CONTRACT,
            "expected_runtime_version": EXPECTED_RUNTIME_VERSION,
            "expected_feature_version": EXPECTED_FEATURE_VERSION,
            "expected_indicator_contract": EXPECTED_INDICATOR_CONTRACT,
            "cache_seconds": _CACHE_SECONDS,
            "cached": bool(_CACHE["value"]),
        }


def install_bot_contract_runtime_v10() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    with _LOCK:
        if _INSTALLED:
            return
        bridge.bot_health = bot_health
        _CACHE["at"] = 0.0
        _CACHE["value"] = {}
        _INSTALLED = True


__all__ = [
    "EXPECTED_CONTRACT",
    "EXPECTED_FEATURE_VERSION",
    "EXPECTED_INDICATOR_CONTRACT",
    "EXPECTED_RUNTIME_VERSION",
    "install_bot_contract_runtime_v10",
    "runtime_status",
]
