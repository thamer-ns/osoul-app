"""Runtime route upgrades for fast SC-aware analysis presentations."""
from __future__ import annotations

_INSTALLED = False


def install_analysis_routes() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # The persistent database snapshot is only a cold-start accelerator. Patch
    # every optional persistence operation before the runtime imports it so a
    # migration/permission failure cannot block the authenticated application.
    from persistent_cache_resilience_v10 import (
        install_persistent_cache_resilience_v10,
    )

    install_persistent_cache_resilience_v10()

    # V9 installs bounded providers, one reusable analysis context, corrected
    # mixed quote batches, background-only persistence and the SC-V91 volume gate
    # before analysis views bind direct function imports.
    from sc_runtime_v9 import install_sc_runtime_v9

    install_sc_runtime_v9()

    # Verify the exact V56 bot runtime rather than accepting a reachable service
    # that lacks failure single-flight or finite stale-data safeguards.
    from bot_contract_runtime_v10 import install_bot_contract_runtime_v10

    install_bot_contract_runtime_v10()

    import views
    from ai_engine_core import bot_bridge_v5 as bridge
    from global_bot_sync_v8 import render_global_bot_sync
    from views import analysis
    from views.analysis import integration_v5 as integration_view

    # integration_v5 imports bot_health directly. Rebind it after installing the
    # V56 probe so a previously imported view cannot retain an obsolete check.
    integration_view.bot_health = bridge.bot_health

    original_router = views.router
    if not getattr(original_router, "_osoli_global_bot_sync_v8", False):

        def router_with_bot_sync() -> None:
            render_global_bot_sync()
            original_router()

        router_with_bot_sync._osoli_global_bot_sync_v8 = True  # type: ignore[attr-defined]
        views.router = router_with_bot_sync

    analysis.SECTION_ROUTES["💰 التحليل المالي"] = (
        "views.analysis.financial_v5",
        "render_financial_dashboard_ui",
        "التحليل المالي متعدد المصادر",
        False,
    )
    analysis.SECTION_ROUTES["🤖 تحليل البوت"] = (
        "views.analysis.bot_remote_v8",
        "render_bot_remote_analysis",
        "تحليل محرك البوت المرتبط",
        True,
    )
    _INSTALLED = True


__all__ = ["install_analysis_routes"]
