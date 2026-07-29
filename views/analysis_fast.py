"""Performance-aware wrapper around the comprehensive analysis workspace."""
from __future__ import annotations

from typing import Any


def view_analysis(finance: Any) -> None:
    import views.analysis as analysis

    from analysis_header_performance_v7 import (
        install_analysis_header_performance,
    )

    install_analysis_header_performance(analysis)
    analysis.SECTION_ROUTES["💰 التحليل المالي"] = (
        "views.analysis.financial_v5",
        "render_financial_dashboard_ui",
        "التحليل المالي",
        False,
    )
    analysis.view_analysis(finance)


__all__ = ["view_analysis"]
