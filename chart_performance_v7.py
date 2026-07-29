"""Render charts from an already loaded dataframe without a second network fetch."""
from __future__ import annotations

import time
from contextvars import ContextVar
from typing import Any

import pandas as pd

from performance_runtime_v7 import record_phase

_ACTIVE_CHART_FRAME: ContextVar[pd.DataFrame | None] = ContextVar(
    "osoli_active_chart_frame", default=None
)
_INSTALLED = False
_ORIGINAL_FETCH = None


def install_chart_performance() -> None:
    global _INSTALLED, _ORIGINAL_FETCH
    if _INSTALLED:
        return
    import charts

    _ORIGINAL_FETCH = charts._fetch_history

    def fetch_history(symbol: str, period: str, interval: str):
        frame = _ACTIVE_CHART_FRAME.get()
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            output = frame.copy(deep=True)
            output.attrs.update(dict(getattr(frame, "attrs", {}) or {}))
            return output
        return _ORIGINAL_FETCH(symbol, period, interval)

    charts._fetch_history = fetch_history
    charts._chart_performance_v7_installed = True
    _INSTALLED = True


def render_chart_from_frame(
    symbol: str,
    frame: pd.DataFrame,
    *,
    period: str,
    interval: str,
) -> Any:
    install_chart_performance()
    import charts

    token = _ACTIVE_CHART_FRAME.set(frame)
    started = time.perf_counter()
    try:
        return charts.render_technical_chart(
            symbol,
            period=period,
            interval=interval,
        )
    finally:
        record_phase(
            symbol,
            interval,
            "chart_render_ms",
            (time.perf_counter() - started) * 1000.0,
        )
        _ACTIVE_CHART_FRAME.reset(token)


__all__ = ["install_chart_performance", "render_chart_from_frame"]
