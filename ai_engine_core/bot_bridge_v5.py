"""Authenticated Osoli ↔ market-bot bridge.

Outbound forwarding remains an explicit user action. Lifecycle updates are
pulled through a stable opaque per-portfolio HMAC channel. Production bot URLs
must use HTTPS, and malformed or locally rejected remote events are quarantined
without allowing one bad record to crash Streamlit synchronization.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Any
from urllib.parse import urlparse

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore[assignment]

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None  # type: ignore[assignment]

from ai_engine_core.bot_sync_state_v6 import load_cursor, save_cursor
from ai_engine_core.compass_contract import parse_compass_payload, to_bot_wire_payload
from ai_engine_core.external_signal_journal_v5 import (
    quarantine_remote_event,
    record_external_event,
)
from tenant_scope import current_tenant

LOGGER = logging.getLogger(__name__)
_SYNC_TOKEN_HEADER = "X-Osoli-Sync-Token"
_SYNC_CHANNEL_HEADER = "X-Osoli-Sync-Channel"
_LOCAL_HTTP_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _secret(name: str) -> str:
    if st is not None:
        try:
            value = st.secrets.get(name, "")  # type: ignore[union-attr]
            if value:
                return str(value).strip()
        except Exception:
            LOGGER.debug("Secret lookup failed for %s", name, exc_info=True)
    return str(os.getenv(name, "") or "").strip()


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _base_url() -> str:
    raw = _secret("SC_BOT_BASE_URL").rstrip("/")
    if not raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return ""
    host = str(parsed.hostname or "").lower()
    if parsed.scheme == "https":
        return raw
    allow_insecure = _truthy(_secret("OSOUL_ALLOW_INSECURE_BOT_HTTP"))
    if parsed.scheme == "http" and (host in _LOCAL_HTTP_HOSTS or allow_insecure):
        return raw
    return ""


def _sync_channel() -> str:
    tenant = current_tenant()
    secret = _secret("SC_BOT_SYNC_SECRET")
    if tenant is None or len(secret) < 32:
        return ""
    # The namespace is a durable identifier, not a software-version marker.
    # Keeping v6 preserves every queued event and active lifecycle created before
    # the V7 journal deployment while the secret and tenant remain unchanged.
    message = f"osoli-sync-v6:{tenant.user_id}:{tenant.portfolio_id}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _sync_headers() -> dict[str, str]:
    token = _secret("SC_BOT_SYNC_TOKEN")
    channel = _sync_channel()
    if len(token) < 32 or not channel:
        return {}
    return {_SYNC_TOKEN_HEADER: token, _SYNC_CHANNEL_HEADER: channel}


def bridge_configuration() -> dict[str, Any]:
    base = _base_url()
    sync_headers = _sync_headers()
    legacy_token = _secret("SC_BOT_TRADINGVIEW_TOKEN")
    parsed = urlparse(base) if base else None
    return {
        "configured": bool(base and (sync_headers or legacy_token)),
        "base_url_configured": bool(base),
        "secure_transport": bool(parsed and parsed.scheme == "https"),
        "legacy_forward_token_configured": bool(legacy_token),
        "sync_configured": bool(base and sync_headers),
        "sync_token_configured": len(_secret("SC_BOT_SYNC_TOKEN")) >= 32,
        "sync_secret_configured": len(_secret("SC_BOT_SYNC_SECRET")) >= 32,
        "sync_channel_contract": "stable-v6",
        "telegram_credentials_stored_in_osoli": False,
        "forwarding_mode": (
            "explicit_send_with_automatic_tenant_pull"
            if sync_headers
            else "legacy_explicit_only"
        ),
    }


def bot_health() -> dict[str, Any]:
    base = _base_url()
    if not base or requests is None:
        return {"ok": False, "reason": "not_configured_or_insecure_url"}
    try:
        response = requests.get(f"{base}/health", timeout=8)
        if response.status_code != 200:
            return {"ok": False, "reason": f"http_{response.status_code}"}
        payload = response.json()
        if not isinstance(payload, dict):
            return {"ok": False, "reason": "invalid_response"}
        return {
            "ok": str(payload.get("status") or "").lower() == "ok",
            "version": payload.get("version"),
            "feed_mode": payload.get("feed_mode"),
            "school_consensus": payload.get("school_consensus"),
            "supported_frames": payload.get("supported_frames"),
            "analysis_journal": payload.get("analysis_journal"),
            "osoli_sync": payload.get("osoli_sync"),
        }
    except Exception:
        LOGGER.info("Bot health check failed", exc_info=True)
        return {"ok": False, "reason": "unreachable"}


def _wire_input(payload: str | bytes | dict[str, Any]) -> str | bytes | dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    if any(key in payload for key in ("s", "e", "sy", "tf", "p")):
        return payload
    if payload.get("source") and payload.get("event"):
        return to_bot_wire_payload(payload)
    return payload


def forward_compass_payload(payload: str | bytes | dict[str, Any]) -> dict[str, Any]:
    base = _base_url()
    if not base or requests is None:
        return {"ok": False, "reason": "bridge_not_configured_or_insecure_url"}
    try:
        parsed = parse_compass_payload(_wire_input(payload))
    except ValueError:
        LOGGER.info("Rejected invalid payload before bot forwarding", exc_info=True)
        return {"ok": False, "reason": "invalid_payload"}
    if bool(parsed.get("replay_event")):
        return {"ok": False, "reason": "historical_replay_not_forwarded"}
    wire = to_bot_wire_payload(parsed)
    sync_headers = _sync_headers()
    legacy_token = _secret("SC_BOT_TRADINGVIEW_TOKEN")
    try:
        if sync_headers:
            response = requests.post(
                f"{base}/integrations/osoli/ingest",
                json=wire,
                headers=sync_headers,
                timeout=12,
            )
            mode = "tenant_sync"
        elif legacy_token:
            response = requests.post(
                f"{base}/webhooks/tradingview/{legacy_token}",
                json=wire,
                timeout=12,
            )
            mode = "legacy_forward"
        else:
            return {"ok": False, "reason": "bridge_not_configured"}
        if response.status_code not in {200, 201}:
            return {"ok": False, "reason": f"http_{response.status_code}"}
        result = response.json()
        if not isinstance(result, dict) or not bool(result.get("ok")):
            return {"ok": False, "reason": "bot_rejected"}
        return {
            "ok": True,
            "created": bool(result.get("created")),
            "event_id": result.get("event_id"),
            "plan_id": result.get("plan_id"),
            "market": result.get("market"),
            "mode": mode,
        }
    except Exception:
        LOGGER.info("Bot forwarding failed", exc_info=True)
        return {"ok": False, "reason": "unreachable"}


def _quarantine(
    channel: str,
    remote_id: int,
    item: Any,
    reason: str,
) -> bool:
    result = quarantine_remote_event(channel, remote_id, item, reason)
    if not result.get("ok"):
        LOGGER.error(
            "Unable to quarantine bot event %s after rejection: %s",
            remote_id,
            result.get("reason"),
        )
        return False
    return True


def _validated_remote_events(events: list[Any]) -> tuple[list[tuple[int, dict[str, Any]]], int]:
    """Parse IDs before sorting so malformed protocol data cannot raise."""
    valid: list[tuple[int, dict[str, Any]]] = []
    rejected = 0
    for item in events:
        if not isinstance(item, dict):
            rejected += 1
            continue
        try:
            remote_id = int(item.get("id"))
        except (TypeError, ValueError, OverflowError):
            rejected += 1
            continue
        if remote_id <= 0:
            rejected += 1
            continue
        valid.append((remote_id, item))
    valid.sort(key=lambda pair: pair[0])
    return valid, rejected


def sync_bot_events(*, limit: int = 100) -> dict[str, Any]:
    """Pull ordered lifecycle updates for the active opaque tenant channel."""
    base = _base_url()
    headers = _sync_headers()
    channel = _sync_channel()
    if not base or not headers or not channel or requests is None:
        return {"ok": False, "reason": "sync_not_configured", "received": 0}
    cursor = load_cursor(channel)
    try:
        response = requests.get(
            f"{base}/integrations/osoli/events",
            headers=headers,
            params={"after": cursor, "limit": max(1, min(250, int(limit)))},
            timeout=12,
        )
        if response.status_code != 200:
            return {"ok": False, "reason": f"http_{response.status_code}", "received": 0}
        body = response.json()
        events = body.get("events") if isinstance(body, dict) else None
        if not isinstance(events, list):
            return {"ok": False, "reason": "invalid_response", "received": 0}
    except Exception:
        LOGGER.info("Bot synchronization pull failed", exc_info=True)
        return {"ok": False, "reason": "unreachable", "received": 0}

    imported = 0
    duplicates = 0
    quarantined = 0
    ordered, protocol_errors = _validated_remote_events(events)
    last_processed = cursor
    for remote_id, item in ordered:
        if remote_id <= last_processed:
            duplicates += 1
            continue
        payload = item.get("payload")
        if not isinstance(payload, dict):
            if not _quarantine(channel, remote_id, item, "invalid_remote_payload"):
                protocol_errors += 1
                break
            quarantined += 1
            last_processed = remote_id
            continue
        stored = record_external_event(
            payload,
            remote_event_id=remote_id,
            remote_channel=channel,
        )
        if not stored.get("ok"):
            reason = str(stored.get("reason") or "local_lifecycle_rejection")
            LOGGER.warning("Bot event %s quarantined by local lifecycle: %s", remote_id, reason)
            if not _quarantine(channel, remote_id, item, reason):
                protocol_errors += 1
                break
            quarantined += 1
            last_processed = remote_id
            continue
        if stored.get("created"):
            imported += 1
        else:
            duplicates += 1
        last_processed = remote_id

    if last_processed > cursor and not save_cursor(channel, last_processed):
        return {
            "ok": False,
            "reason": "cursor_write_failed",
            "received": imported,
            "duplicates": duplicates,
            "quarantined": quarantined,
            "rejected": protocol_errors,
            "cursor": cursor,
        }
    ok = protocol_errors == 0
    reason = (
        "protocol_error"
        if not ok
        else "completed_with_quarantine"
        if quarantined
        else None
    )
    return {
        "ok": ok,
        "reason": reason,
        "received": imported,
        "duplicates": duplicates,
        "quarantined": quarantined,
        "rejected": protocol_errors,
        "cursor": last_processed,
        "has_more": bool(body.get("has_more")) if isinstance(body, dict) else False,
    }


__all__ = [
    "bot_health",
    "bridge_configuration",
    "forward_compass_payload",
    "sync_bot_events",
]
