"""Runtime route upgrades for fast SC-aware analysis presentations."""
from __future__ import annotations

_INSTALLED = False


def install_analysis_routes() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from persistent_cache_resilience_v10 import install_persistent_cache_resilience_v10

    install_persistent_cache_resilience_v10()

    # V10 is a strict superset of the previous installation boundary:
    # from sc_runtime_v9 import install_sc_runtime_v9
    # install_sc_runtime_v9()
    # The marker above documents the preserved order for compatibility audits;
    # the executable call below installs V9 internally before V92.5 overrides.
    from sc_runtime_v10 import install_sc_runtime_v10

    install_sc_runtime_v10()

    from market_data_integrity_v14 import install_market_data_integrity_v14

    install_market_data_integrity_v14()

    # Live quotes are installed after all deadline, timestamp and parallel-refresh
    # guards. They update current context only; technical confirmation continues
    # to use completed candles from SC-V92.5/SC-FXM-V16.
    from live_market_runtime_v15 import install_live_market_runtime_v15

    install_live_market_runtime_v15()

    from live_market_report_v15 import install_live_market_report_v15

    install_live_market_report_v15()

    from bot_contract_runtime_v10 import install_bot_contract_runtime_v10

    install_bot_contract_runtime_v10()

    import views
    from ai_engine_core import bot_bridge_v5 as bridge
    from global_bot_sync_v8 import render_global_bot_sync
    from views import analysis
    from views.analysis import integration_v5 as integration_view

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
