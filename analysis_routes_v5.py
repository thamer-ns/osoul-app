"""Runtime route upgrades for fast SC-aware analysis presentations."""
from __future__ import annotations

_INSTALLED = False


def install_analysis_routes() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # Install before importing the analysis package. Several views import market
    # and bot functions directly, so the bounded providers and report hook must
    # already be active when those modules bind their globals.
    from sc_runtime_v8 import install_sc_runtime_v8

    install_sc_runtime_v8()

    import views
    from global_bot_sync_v8 import render_global_bot_sync
    from views import analysis

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
    _INSTALLED = True


__all__ = ["install_analysis_routes"]
