"""On-demand authenticated analysis call from Osoli to the market bot."""
from __future__ import annotations

import logging
from typing import Any

from ai_engine_core import bot_bridge_v5 as bridge

LOGGER = logging.getLogger(__name__)


def request_bot_analysis(symbol: str, timeframe: str) -> dict[str, Any]:
    base = bridge._base_url()  # noqa: SLF001
    headers = bridge._sync_headers()  # noqa: SLF001
    if not base or not headers or bridge.requests is None:
        return {"ok": False, "reason": "sync_not_configured"}
    try:
        response = bridge.requests.post(
            f"{base}/integrations/osoli/analysis",
            headers=headers,
            json={
                "symbol": str(symbol or "").strip().upper(),
                "frame": str(timeframe or "1d").strip().lower(),
            },
            timeout=8.5,
        )
        if response.status_code != 200:
            return {
                "ok": False,
                "reason": f"http_{response.status_code}",
            }
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("ok"):
            return {"ok": False, "reason": "invalid_response"}
        return payload
    except Exception:
        LOGGER.info("Remote bot analysis failed", exc_info=True)
        return {"ok": False, "reason": "unreachable"}


__all__ = ["request_bot_analysis"]
