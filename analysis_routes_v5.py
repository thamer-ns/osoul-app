"""Small runtime route upgrade for v5 analysis presentations."""
from __future__ import annotations

_INSTALLED = False


def install_analysis_routes() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from views import analysis

    analysis.SECTION_ROUTES["💰 التحليل المالي"] = (
        "views.analysis.financial_v5",
        "render_financial_dashboard_ui",
        "التحليل المالي متعدد المصادر",
        False,
    )
    _INSTALLED = True


__all__ = ["install_analysis_routes"]
