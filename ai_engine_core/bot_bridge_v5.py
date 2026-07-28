"""Authenticated Osoli ↔ market-bot bridge.

Osoli never stores Telegram credentials.  A user action still controls outbound
forwarding, while bot lifecycle updates are pulled automatically through an
opaque per-portfolio HMAC channel.  Raw user and portfolio identifiers are never
sent to the bot and sync tokens are sent in headers rather than URL paths.
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
from ai_engine_core.external_signal_journal_v5 import record_external_event
from tenant_scope import current_tenant

LOGGER = logging.getLogger(__name__)
_ALLOWED_SCHEMES = {"https", "http"}
_SYNC_TOKEN_HEADER = "X-Osoli-Sync-Token"
_SYNC_CHANNEL_HEADER = "X-Osoli-Sync-Channel"


def _secret(name: str) -> str:
    if st is not None:
        try:
            value = st.secrets.get(name, "")  # type: ignore[union-attr]
            if value:
                return str(value).strip()
        except Exception:
            LOGGER.debug("Secret lookup failed for %s", name, exc_info=True)
    return str(os.getenv(name, "") or "").strip()


def _base_url() -> str:
    raw = _secret("SC_BOT_BASE_URL").rstrip("/")
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.netloc:
        return ""
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return ""
    return raw


def _sync_channel() -> str:
    tenant = current_tenant()
    secret = _secret("SC_BOT_SYNC_SECRET")
    if tenant is None or len(secret) < 32:
        return ""
    message = f"osoli-sync-v6:{tenant.user_id}:{tenant.portfolio_id}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _sync_headers() -> dict[str, str]:
    token = _secret("SC_BOT_SYNC_TOKEN")
    channel = _sync_channel()
    if not token or not channel:
        return {}
    return {_SYNC_TOKEN_HEADER: token, _SYNC_CHANNEL_HEADER: channel}


def bridge_configuration() -> dict[str, Any]:
    base = _base_url()
    sync_headers = _sync_headers()
    legacy_token = _secret("SC_BOT_TRADINGVIEW_TOKEN")
    return {
        "configured": bool(base and (sync_headers or legacy_token)),
        "base_url_configured": bool(base),
        "legacy_forward_token_configured": bool(legacy_token),
        "sync_configured": bool(base and sync_headers),
        "sync_token_configured": bool(_secret("SC_BOT_SYNC_TOKEN")),
        "sync_secret_configured": len(_secret("SC_BOT_SYNC_SECRET")) >= 32,
        "telegram_credentials_stored_in_osoli": False,
        "forwarding_mode": "explicit_send_with_automatic_tenant_pull" if sync_headers else "legacy_explicit_only",
    }


def bot_health() -> dict[str, Any]:
    base = _base_url()
    if not base or requests is None:
        return {"ok": False, "reason": "not_configured"}
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


def forward_compass_payload(payload: str | bytes | dict[str, Any]) -> dict[str, Any]:
    base = _base_url()
    if not base or requests is None:
        return {"ok": False, "reason": "bridge_not_configured"}
    try:
        parsed = parse_compass_payload(payload)
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
        if response.status_code != 200:
            return {"ok": False, "reason": f"http_{response.status_code}"}
        result = response.json()
        if not isinstance(result, dict) or not bool(result.get("ok")):
            return {"ok": False, "reason": "bot_rejected"}
        return {
            "ok": True,
            "created": bool(result.get("created")),
            "event_id": result.get("event_id"),
            "market": result.get("market"),
            "mode": mode,
        }
    except Exception:
        LOGGER.info("Bot forwarding failed", exc_info=True)
        return {"ok": False, "reason": "unreachable"}


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
    rejected = 0
    last_contiguous = cursor
    for item in sorted(events, key=lambda value: int((value or {}).get("id") or 0)):
        if not isinstance(item, dict):
            rejected += 1
            break
        remote_id = int(item.get("id") or 0)
        payload = item.get("payload")
        if remote_id <= last_contiguous or not isinstance(payload, dict):
            rejected += 1
            break
        stored = record_external_event(
            payload,
            remote_event_id=remote_id,
            remote_channel=channel,
        )
        if not stored.get("ok"):
            LOGGER.warning("Bot event %s rejected by local lifecycle: %s", remote_id, stored.get("reason"))
            rejected += 1
            break
        if stored.get("created"):
            imported += 1
        else:
            duplicates += 1
        last_contiguous = remote_id

    if last_contiguous > cursor and not save_cursor(channel, last_contiguous):
        return {
            "ok": False,
            "reason": "cursor_write_failed",
            "received": imported,
            "duplicates": duplicates,
            "rejected": rejected,
        }
    return {
        "ok": rejected == 0,
        "reason": None if rejected == 0 else "event_rejected",
        "received": imported,
        "duplicates": duplicates,
        "rejected": rejected,
        "cursor": last_contiguous,
        "has_more": bool(body.get("has_more")) if isinstance(body, dict) else False,
    }


__all__ = [
    "bot_health",
    "bridge_configuration",
    "forward_compass_payload",
    "sync_bot_events",
]
