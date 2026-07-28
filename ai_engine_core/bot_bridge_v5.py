"""Optional, explicit bridge from Osoli to the market-bot service.

Osoli never embeds Telegram credentials.  It can health-check the separately
hosted FastAPI bot and, only after an explicit UI action, forward a validated
SC-V90 payload to the bot's authenticated TradingView endpoint.  Tokens are read
from Secrets/environment and are never returned or logged.
"""
from __future__ import annotations

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

from ai_engine_core.compass_contract import parse_compass_payload

LOGGER = logging.getLogger(__name__)
_ALLOWED_SCHEMES = {"https", "http"}


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
    if parsed.username or parsed.password:
        return ""
    return raw


def bridge_configuration() -> dict[str, Any]:
    base = _base_url()
    return {
        "configured": bool(base and _secret("SC_BOT_TRADINGVIEW_TOKEN")),
        "base_url_configured": bool(base),
        "token_configured": bool(_secret("SC_BOT_TRADINGVIEW_TOKEN")),
        "telegram_credentials_stored_in_osoli": False,
        "forwarding_mode": "explicit_only",
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
        }
    except Exception:
        LOGGER.info("Bot health check failed", exc_info=True)
        return {"ok": False, "reason": "unreachable"}


def forward_compass_payload(payload: str | bytes | dict[str, Any]) -> dict[str, Any]:
    base = _base_url()
    token = _secret("SC_BOT_TRADINGVIEW_TOKEN")
    if not base or not token or requests is None:
        return {"ok": False, "reason": "bridge_not_configured"}
    try:
        parsed = parse_compass_payload(payload)
    except ValueError:
        LOGGER.info("Rejected invalid payload before bot forwarding", exc_info=True)
        return {"ok": False, "reason": "invalid_payload"}
    # Rebuild the compact wire contract expected by the bot.  This avoids
    # forwarding UI-only fields or an untrusted original object.
    targets = list(parsed.get("targets") or [])[:3]
    targets += [None] * (3 - len(targets))
    wire = {
        "v": parsed.get("schema_version"),
        "s": parsed.get("source"),
        "e": parsed.get("event"),
        "x": parsed.get("symbol"),
        "y": parsed.get("asset_type"),
        "f": parsed.get("timeframe"),
        "t": parsed.get("event_timestamp_ms"),
        "p": parsed.get("event_price"),
        "d": parsed.get("direction_code"),
        "en": parsed.get("entry"),
        "sl": parsed.get("stop"),
        "t1": targets[0],
        "t2": targets[1],
        "t3": targets[2],
        "n": parsed.get("target_count"),
        "q": parsed.get("score"),
        "qm": parsed.get("score_maximum"),
        "ct": parsed.get("counter_trend"),
    }
    try:
        response = requests.post(
            f"{base}/webhooks/tradingview/{token}",
            json=wire,
            timeout=12,
        )
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
        }
    except Exception:
        LOGGER.info("Bot forwarding failed", exc_info=True)
        return {"ok": False, "reason": "unreachable"}


__all__ = [
    "bot_health",
    "bridge_configuration",
    "forward_compass_payload",
]
