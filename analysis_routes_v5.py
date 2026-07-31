"""Fail-open runtime upgrades used by the practical analysis workspace."""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

LOGGER = logging.getLogger(__name__)
_INSTALLED = False
_FAILURES: list[str] = []


def _attempt(
    name: str,
    operation: Callable[[], None],
    failures: list[str],
) -> None:
    try:
        operation()
    except Exception:
        LOGGER.exception("Optional analysis runtime component failed: %s", name)
        failures.append(name)


def _install_global_bot_sync(views_module: Any) -> bool:
    """Attach background bot sync without making analysis rendering depend on it."""
    try:
        from global_bot_sync_v8 import render_global_bot_sync

        original_router = views_module.router
        if getattr(original_router, "_osoli_global_bot_sync_v8", False):
            return True

        def router_with_bot_sync() -> None:
            try:
                render_global_bot_sync()
            except Exception:
                LOGGER.exception("Global bot sync render failed")
            original_router()

        router_with_bot_sync._osoli_global_bot_sync_v8 = True  # type: ignore[attr-defined]
        views_module.router = router_with_bot_sync
        return True
    except Exception:
        LOGGER.exception("Optional global bot sync installation failed")
        return False


def install_analysis_routes() -> None:
    """Install enhancements in audited order while preserving the base page."""
    global _INSTALLED, _FAILURES
    if _INSTALLED:
        return

    failures: list[str] = []

    # Persistent fallback must exist before the SC router starts using caches.
    from persistent_cache_resilience_v10 import (
        install_persistent_cache_resilience_v10,
    )

    _attempt(
        "persistent_cache",
        lambda: install_persistent_cache_resilience_v10(),
        failures,
    )

    # V9 installs the bounded Twelve Data layer before the SC V8 runtime.
    from sc_runtime_v9 import install_sc_runtime_v9

    _attempt("sc_runtime", lambda: install_sc_runtime_v9(), failures)

    # Integrity wraps the installed SC providers and therefore follows V9.
    from market_data_integrity_v14 import install_market_data_integrity_v14

    _attempt(
        "market_integrity",
        lambda: install_market_data_integrity_v14(),
        failures,
    )

    from live_market_runtime_v17 import install_live_market_runtime_v17

    _attempt(
        "live_market",
        lambda: install_live_market_runtime_v17(),
        failures,
    )

    from live_market_report_v17 import install_live_market_report_v17

    _attempt(
        "live_report",
        lambda: install_live_market_report_v17(),
        failures,
    )

    # Contract validation comes after the market and report overlays.
    from bot_contract_runtime_v10 import install_bot_contract_runtime_v10

    _attempt(
        "bot_contract",
        lambda: install_bot_contract_runtime_v10(),
        failures,
    )

    # UI imports happen only after all runtime/data layers are prepared.
    import views

    if not _install_global_bot_sync(views):
        failures.append("global_bot_sync")

    _FAILURES = failures
    _INSTALLED = True


def runtime_status() -> dict[str, Any]:
    return {
        "installed": _INSTALLED,
        "fail_open": True,
        "analysis_entry_independent": True,
        "failed_components": list(_FAILURES),
        "user_sections": ["analysis", "evaluation"],
    }


__all__ = ["install_analysis_routes", "runtime_status"]
