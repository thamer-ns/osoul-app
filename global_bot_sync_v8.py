"""Non-blocking tenant-scoped bot reconciliation for authenticated pages.

The first V8 implementation called the remote bot synchronously whenever the
Streamlit router reran.  A slow or sleeping bot could therefore add the full
HTTP timeout to navigation, widgets and analysis rendering.  This module keeps
the 60-second reconciliation contract while moving network and journal work to
a bounded, context-aware single-flight pool.
"""
from __future__ import annotations

import copy
import logging
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import copy_context
from typing import Any

import streamlit as st

from ai_engine_core import bot_bridge_v5 as bridge

LOGGER = logging.getLogger(__name__)
_MAX_WORKERS = max(1, min(4, int(os.getenv("OSOUL_BOT_SYNC_WORKERS", "2"))))
_MIN_INTERVAL_SECONDS = max(
    15.0,
    min(900.0, float(os.getenv("OSOUL_BOT_SYNC_INTERVAL_SECONDS", "60"))),
)
_SYNC_EXECUTOR = ThreadPoolExecutor(
    max_workers=_MAX_WORKERS,
    thread_name_prefix="osoli-bot-sync-v9",
)
_SYNC_LOCK = threading.RLock()
_INFLIGHT: dict[str, Future[Any]] = {}
_LAST_STARTED: dict[str, float] = {}
_LAST_COMPLETED: dict[str, float] = {}
_LAST_RESULT: dict[str, dict[str, Any]] = {}


def _safe_result(result: Any) -> dict[str, Any]:
    payload = result if isinstance(result, dict) else {}
    return {
        "ok": bool(payload.get("ok")),
        "reason": payload.get("reason"),
        "received": int(payload.get("received") or 0),
        "duplicates": int(payload.get("duplicates") or 0),
        "quarantined": int(payload.get("quarantined") or 0),
        "rejected": int(payload.get("rejected") or 0),
        "cursor": int(payload.get("cursor") or 0),
        "has_more": bool(payload.get("has_more")),
    }


def _failed_result(reason: str) -> dict[str, Any]:
    return {
        "ok": False,
        "reason": reason,
        "received": 0,
        "duplicates": 0,
        "quarantined": 0,
        "rejected": 0,
        "cursor": 0,
        "has_more": False,
    }


def _reap_completed_locked(now: float) -> None:
    for channel, future in list(_INFLIGHT.items()):
        if not future.done():
            continue
        _INFLIGHT.pop(channel, None)
        try:
            result = _safe_result(future.result())
        except Exception:
            LOGGER.info("Global bot reconciliation worker failed", exc_info=True)
            result = _failed_result("worker_failure")
        _LAST_RESULT[channel] = result
        _LAST_COMPLETED[channel] = now

    # Keep process-global state bounded when many tenant channels visit a worker.
    if len(_LAST_RESULT) > 256:
        oldest = sorted(
            _LAST_COMPLETED,
            key=lambda key: _LAST_COMPLETED.get(key, 0.0),
        )[:64]
        for channel in oldest:
            if channel in _INFLIGHT:
                continue
            _LAST_RESULT.pop(channel, None)
            _LAST_STARTED.pop(channel, None)
            _LAST_COMPLETED.pop(channel, None)


def _submit_locked(channel: str, now: float) -> bool:
    running = sum(not future.done() for future in _INFLIGHT.values())
    if running >= _MAX_WORKERS:
        return False
    # ContextVars do not propagate to executor threads automatically.  Copying
    # the current context preserves the already-authenticated tenant scope while
    # keeping user/portfolio identifiers out of the remote request.
    context = copy_context()
    future = _SYNC_EXECUTOR.submit(
        context.run,
        bridge.sync_bot_events,
        limit=100,
    )
    _INFLIGHT[channel] = future
    _LAST_STARTED[channel] = now
    return True


def poll_global_bot_sync(*, now: float | None = None) -> dict[str, Any]:
    """Return immediately and schedule at most one sync per opaque channel."""
    try:
        config = bridge.bridge_configuration()
    except Exception:
        LOGGER.info("Bot bridge configuration failed", exc_info=True)
        return {**_failed_result("configuration_error"), "pending": False}
    if not config.get("sync_configured"):
        return {**_failed_result("sync_not_configured"), "pending": False}

    try:
        channel = bridge._sync_channel()  # noqa: SLF001
    except Exception:
        LOGGER.info("Unable to resolve opaque bot sync channel", exc_info=True)
        channel = ""
    if not channel:
        return {**_failed_result("channel_unavailable"), "pending": False}

    current = time.monotonic() if now is None else float(now)
    with _SYNC_LOCK:
        _reap_completed_locked(current)
        future = _INFLIGHT.get(channel)
        pending = bool(future is not None and not future.done())
        last_started = _LAST_STARTED.get(channel, 0.0)
        due = not last_started or current - last_started >= _MIN_INTERVAL_SECONDS
        scheduled = False
        if not pending and due:
            scheduled = _submit_locked(channel, current)
            pending = scheduled

        result = copy.deepcopy(_LAST_RESULT.get(channel))
        completed_at = _LAST_COMPLETED.get(channel)
        active_count = sum(
            not item.done() for item in _INFLIGHT.values()
        )

    if result is None:
        reason = "sync_scheduled" if scheduled else "sync_capacity_busy"
        result = _failed_result(reason)
    result.update(
        {
            "pending": pending,
            "scheduled": scheduled,
            "nonblocking": True,
            "active_workers": active_count,
            "max_workers": _MAX_WORKERS,
            "last_completed_monotonic": completed_at,
        }
    )
    return result


@st.fragment(run_every="60s")
def render_global_bot_sync() -> None:
    """Poll completed work and schedule reconciliation without blocking UI."""
    try:
        st.session_state["_global_bot_sync_v8"] = poll_global_bot_sync()
    except Exception:
        LOGGER.info("Global bot reconciliation scheduling failed", exc_info=True)
        st.session_state["_global_bot_sync_v8"] = {
            **_failed_result("scheduler_failure"),
            "pending": False,
            "nonblocking": True,
        }


__all__ = ["poll_global_bot_sync", "render_global_bot_sync"]
