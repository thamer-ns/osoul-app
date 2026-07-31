"""Runtime route upgrades for fast SC-aware analysis presentations."""
from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

_INSTALLED = False


def _install_legacy_section_routes(analysis: Any) -> None:
    """Upgrade the retired tab workspace only when it is actually present.

    V18 replaced ``SECTION_ROUTES`` with one practical decision workspace. A
    hard reference to the removed mapping made the optional ``analysis_routes``
    bootstrap fail and forced the whole application into safe mode. Keeping the
    legacy mutation behind capability detection supports warm processes during
    a deployment while allowing the current workspace to load normally.
    """
    routes = getattr(analysis, "SECTION_ROUTES", None)
    if not isinstance(routes, MutableMapping):
        if not callable(getattr(analysis, "view_analysis", None)):
            raise RuntimeError("analysis workspace has no callable entry point")
        return

    routes["💰 التحليل المالي"] = (
        "views.analysis.financial_v5",
        "render_financial_dashboard_ui",
        "التحليل المالي متعدد المصادر",
        False,
    )
    routes["🤖 تحليل البوت"] = (
        "views.analysis.bot_remote_v8",
        "render_bot_remote_analysis",
        "تحليل محرك البوت المرتبط",
        True,
    )


def install_analysis_routes() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from persistent_cache_resilience_v10 import install_persistent_cache_resilience_v10

    install_persistent_cache_resilience_v10()

    # Preserve the proven V9 installation boundary and ordering. The current
    # SC-V92.5 overlays remain installed inside that chain before V17 attaches
    # the live-price sidecar.
    from sc_runtime_v9 import install_sc_runtime_v9

    install_sc_runtime_v9()

    from market_data_integrity_v14 import install_market_data_integrity_v14

    install_market_data_integrity_v14()

    # V17 keeps the completed-candle price immutable and exposes SAHMK/Twelve
    # Data as a separate live sidecar with correct spread semantics.
    from live_market_runtime_v17 import install_live_market_runtime_v17

    install_live_market_runtime_v17()

    from live_market_report_v17 import install_live_market_report_v17

    install_live_market_report_v17()

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

    _install_legacy_section_routes(analysis)
    _INSTALLED = True


__all__ = ["install_analysis_routes"]
