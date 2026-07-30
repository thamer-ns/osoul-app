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

    from views import analysis

    analysis.SECTION_ROUTES["💰 التحليل المالي"] = (
        "views.analysis.financial_v5",
        "render_financial_dashboard_ui",
        "التحليل المالي متعدد المصادر",
        False,
    )
    _INSTALLED = True


__all__ = ["install_analysis_routes"]
