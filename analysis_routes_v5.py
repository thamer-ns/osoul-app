"""Fail-open runtime upgrades used by the practical analysis workspace."""
from __future__ import annotations

import importlib
import logging
from typing import Any

LOGGER = logging.getLogger(__name__)
_INSTALLED = False
_FAILURES: list[str] = []

_RUNTIME_INSTALLERS: tuple[tuple[str, str, str], ...] = (
    (
        "persistent_cache",
        "persistent_cache_resilience_v10",
        "install_persistent_cache_resilience_v10",
    ),
    ("sc_runtime", "sc_runtime_v9", "install_sc_runtime_v9"),
    (
        "market_integrity",
        "market_data_integrity_v14",
        "install_market_data_integrity_v14",
    ),
    (
        "live_market",
        "live_market_runtime_v17",
        "install_live_market_runtime_v17",
    ),
    (
        "live_report",
        "live_market_report_v17",
        "install_live_market_report_v17",
    ),
    (
        "bot_contract",
        "bot_contract_runtime_v10",
        "install_bot_contract_runtime_v10",
    ),
)


def _install_component(
    name: str,
    module_name: str,
    function_name: str,
) -> bool:
    try:
        module = importlib.import_module(module_name)
        installer = getattr(module, function_name)
        if not callable(installer):
            raise TypeError(f"installer is not callable: {function_name}")
        installer()
        return True
    except Exception:
        LOGGER.exception("Optional analysis runtime component failed: %s", name)
        return False


def _install_global_bot_sync() -> bool:
    """Attach background bot sync without making analysis rendering depend on it."""
    try:
        import views
        from global_bot_sync_v8 import render_global_bot_sync

        original_router = views.router
        if getattr(original_router, "_osoli_global_bot_sync_v8", False):
            return True

        def router_with_bot_sync() -> None:
            try:
                render_global_bot_sync()
            except Exception:
                LOGGER.exception("Global bot sync render failed")
            original_router()

        router_with_bot_sync._osoli_global_bot_sync_v8 = True  # type: ignore[attr-defined]
        views.router = router_with_bot_sync
        return True
    except Exception:
        LOGGER.exception("Optional global bot sync installation failed")
        return False


def install_analysis_routes() -> None:
    """Install analysis enhancements while preserving the base analysis page.

    This stage is optional by design. A provider, cache, bot or presentation
    enhancement must never remove the comprehensive-analysis entry point.
    """
    global _INSTALLED, _FAILURES
    if _INSTALLED:
        return

    failures: list[str] = []
    for name, module_name, function_name in _RUNTIME_INSTALLERS:
        if not _install_component(name, module_name, function_name):
            failures.append(name)
    if not _install_global_bot_sync():
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
