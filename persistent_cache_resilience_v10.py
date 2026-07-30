"""Fail-open installer for the optional persistent public-market cache.

The process cache and bounded providers are the correctness path. PostgreSQL or
SQLite persistence only accelerates cold starts, so a migration/permission error
must never prevent an authenticated Osoli session from opening or add repeated
failed database work to every market request.
"""
from __future__ import annotations

import logging
import sys
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
_ORIGINAL_SAVE_HISTORY = cache.save_history
_ORIGINAL_LOAD_HISTORY = cache.load_history
_ORIGINAL_SAVE_QUOTE = cache.save_quote
_ORIGINAL_LOAD_QUOTE = cache.load_quote
_ORIGINAL_PRUNE = cache.prune_expired


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


def _safe_save_history(*args: Any, **kwargs: Any) -> bool:
    if not _guarded_install():
        return False
    return bool(_ORIGINAL_SAVE_HISTORY(*args, **kwargs))


def _safe_load_history(*args: Any, **kwargs: Any) -> Any:
    if not _guarded_install():
        return None
    return _ORIGINAL_LOAD_HISTORY(*args, **kwargs)


def _safe_save_quote(*args: Any, **kwargs: Any) -> bool:
    if not _guarded_install():
        return False
    return bool(_ORIGINAL_SAVE_QUOTE(*args, **kwargs))


def _safe_load_quote(*args: Any, **kwargs: Any) -> Any:
    if not _guarded_install():
        return None
    return _ORIGINAL_LOAD_QUOTE(*args, **kwargs)


def _safe_prune(*args: Any, **kwargs: Any) -> None:
    if not _guarded_install():
        return
    _ORIGINAL_PRUNE(*args, **kwargs)


def runtime_status() -> dict[str, Any]:
    with _LOCK:
        return {
            "installed": _INSTALLED,
            "available": _AVAILABLE,
            "last_error": _LAST_ERROR or None,
            "fail_open": True,
            "short_circuit_unavailable_operations": True,
            "retry_seconds": _RETRY_SECONDS,
        }


def _patch_loaded_runtime() -> None:
    loaded_runtime = sys.modules.get("sc_runtime_v8")
    if loaded_runtime is None:
        return
    setattr(loaded_runtime, "install_persistent_market_cache", _guarded_install)
    setattr(loaded_runtime, "save_history", _safe_save_history)
    setattr(loaded_runtime, "load_history", _safe_load_history)
    setattr(loaded_runtime, "save_quote", _safe_save_quote)
    setattr(loaded_runtime, "load_quote", _safe_load_quote)
    setattr(loaded_runtime, "prune_expired", _safe_prune)


def install_persistent_cache_resilience_v10() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    with _LOCK:
        if _INSTALLED:
            return
        # Deliberate runtime patch: sc_runtime_v8 normally imports these symbols
        # afterward. Patch already-bound globals too for test/reload paths.
        cache.install_persistent_market_cache = _guarded_install  # type: ignore[assignment]
        cache.save_history = _safe_save_history  # type: ignore[assignment]
        cache.load_history = _safe_load_history  # type: ignore[assignment]
        cache.save_quote = _safe_save_quote  # type: ignore[assignment]
        cache.load_quote = _safe_load_quote  # type: ignore[assignment]
        cache.prune_expired = _safe_prune  # type: ignore[assignment]
        _patch_loaded_runtime()
        _INSTALLED = True


__all__ = [
    "install_persistent_cache_resilience_v10",
    "runtime_status",
]
