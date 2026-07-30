"""Fail-open installer for the optional persistent public-market cache.

The process cache and bounded providers are the correctness path. PostgreSQL or
SQLite persistence only accelerates cold starts, so a migration/permission error
must never prevent an authenticated Osoli session from opening.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

import persistent_market_cache_v8 as cache

LOGGER = logging.getLogger(__name__)
_LOCK = threading.RLock()
_INSTALLED = False
_AVAILABLE: bool | None = None
_LAST_ERROR = ""
_NEXT_RETRY = 0.0
_RETRY_SECONDS = 60.0
_ORIGINAL_INSTALL = cache.install_persistent_market_cache


def _guarded_install() -> bool:
    global _AVAILABLE, _LAST_ERROR, _NEXT_RETRY
    now = time.monotonic()
    with _LOCK:
        if _AVAILABLE is False and now < _NEXT_RETRY:
            return False
        try:
            _ORIGINAL_INSTALL()
        except Exception as exc:
            _AVAILABLE = False
            _LAST_ERROR = type(exc).__name__
            _NEXT_RETRY = now + _RETRY_SECONDS
            LOGGER.warning(
                "Persistent market cache unavailable; continuing with process cache",
                exc_info=True,
            )
            return False
        _AVAILABLE = True
        _LAST_ERROR = ""
        _NEXT_RETRY = 0.0
        return True


def runtime_status() -> dict[str, Any]:
    with _LOCK:
        return {
            "installed": _INSTALLED,
            "available": _AVAILABLE,
            "last_error": _LAST_ERROR or None,
            "fail_open": True,
            "retry_seconds": _RETRY_SECONDS,
        }


def install_persistent_cache_resilience_v10() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    with _LOCK:
        if _INSTALLED:
            return
        # Deliberate runtime patch: sc_runtime_v8 imports this symbol after the
        # guard is installed, so all later cache attempts inherit fail-open behavior.
        cache.install_persistent_market_cache = _guarded_install  # type: ignore[assignment]
        _INSTALLED = True


__all__ = [
    "install_persistent_cache_resilience_v10",
    "runtime_status",
]
