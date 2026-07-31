"""Performance-aware wrapper around the practical analysis workspace."""
from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any


def _upgrade_legacy_routes(analysis: Any) -> None:
    """Keep old warm Streamlit sessions compatible without requiring tabs."""
    routes = getattr(analysis, "SECTION_ROUTES", None)
    if isinstance(routes, MutableMapping):
        routes["💰 التحليل المالي"] = (
            "views.analysis.financial_v5",
            "render_financial_dashboard_ui",
            "التحليل المالي",
            False,
        )


def view_analysis(finance: Any) -> None:
    import views.analysis as analysis

    from analysis_header_performance_v7 import (
        install_analysis_header_performance,
    )

    install_analysis_header_performance(analysis)
    _upgrade_legacy_routes(analysis)

    renderer = getattr(analysis, "view_analysis", None)
    if not callable(renderer):
        raise RuntimeError("analysis workspace entry point is unavailable")
    renderer(finance)


__all__ = ["view_analysis"]
