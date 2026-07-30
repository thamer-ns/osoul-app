"""Authoritative low-latency discovery of the linked bot runtime contract."""
from __future__ import annotations

import copy
import logging
import threading
import time
from typing import Any

from ai_engine_core import bot_bridge_v5 as bridge

LOGGER = logging.getLogger(__name__)
EXPECTED_CONTRACT = "SC-V90-v1-plan-isolation-v56"
EXPECTED_RUNTIME_VERSION = "56.0"
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
    remote_analysis = body.get("remote_analysis") is True
    tenant_safe = body.get("tenant_ids_received") is False
    token_safe = body.get("token_in_url") is False
    installed = runtime.get("installed") is True
    runtime_version = str(runtime.get("runtime_version") or "")
    failure_single_flight = runtime.get("failure_single_flight") is True
    stale_bounded = runtime.get("stale_fallback_age_bounded") is True
    contract_ok = contract == EXPECTED_CONTRACT
    runtime_ok = runtime_version == EXPECTED_RUNTIME_VERSION
    ok = bool(
        contract_ok
        and remote_analysis
        and tenant_safe
        and token_safe
        and installed
        and runtime_ok
        and failure_single_flight
        and stale_bounded
    )
    reason = None
    if not contract_ok:
        reason = "contract_mismatch"
    elif not remote_analysis:
        reason = "remote_analysis_disabled"
    elif not tenant_safe or not token_safe:
        reason = "unsafe_contract_flags"
    elif not installed:
        reason = "runtime_not_installed"
    elif not runtime_ok:
        reason = "runtime_version_mismatch"
    elif not failure_single_flight:
        reason = "failure_single_flight_missing"
    elif not stale_bounded:
        reason = "stale_fallback_unbounded"
    return {
        "ok": ok,
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
        "feature_version": runtime.get("feature_version"),
        "runtime_version": runtime_version or None,
        "runtime_installed": installed,
        "failure_single_flight": failure_single_flight,
        "stale_fallback_age_bounded": stale_bounded,
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
        _INSTALLED = True


__all__ = [
    "EXPECTED_CONTRACT",
    "EXPECTED_RUNTIME_VERSION",
    "install_bot_contract_runtime_v10",
    "runtime_status",
]
