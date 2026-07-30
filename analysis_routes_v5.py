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
    from bounded_twelvedata_v9 import install_bounded_twelvedata_v9
    from sc_runtime_v8 import install_sc_runtime_v8

    # Twelve Data's legacy helper can retry SDK + HTTP paths for much longer than
    # an interactive request. Replace only its adapters with one bounded HTTP
    # request before V8 captures the provider adapter table.
    install_bounded_twelvedata_v9()
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
    analysis.SECTION_ROUTES["🤖 تحليل البوت"] = (
        "views.analysis.bot_remote_v8",
        "render_bot_remote_analysis",
        "تحليل محرك البوت المرتبط",
        True,
    )
    _INSTALLED = True


__all__ = ["install_analysis_routes"]
