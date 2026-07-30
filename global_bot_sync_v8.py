"""Silent tenant-scoped bot reconciliation across every authenticated page."""
from __future__ import annotations

import logging
from typing import Any

import streamlit as st

from ai_engine_core.bot_bridge_v5 import (
    bridge_configuration,
    sync_bot_events,
)

LOGGER = logging.getLogger(__name__)


@st.fragment(run_every="60s")
def render_global_bot_sync() -> None:
    """Pull lifecycle events while any authenticated Osoli page stays open."""
    try:
        config = bridge_configuration()
        if not config.get("sync_configured"):
            return
        result = sync_bot_events(limit=100)
        safe: dict[str, Any] = {
            "ok": bool(result.get("ok")),
            "reason": result.get("reason"),
            "received": int(result.get("received") or 0),
            "duplicates": int(result.get("duplicates") or 0),
            "quarantined": int(result.get("quarantined") or 0),
            "cursor": int(result.get("cursor") or 0),
        }
        st.session_state["_global_bot_sync_v8"] = safe
    except Exception:
        LOGGER.info("Global bot reconciliation failed", exc_info=True)
        st.session_state["_global_bot_sync_v8"] = {
            "ok": False,
            "reason": "unreachable",
        }


__all__ = ["render_global_bot_sync"]
