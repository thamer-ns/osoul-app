"""Unified overview v5 plus persistent indicator/bot workspace."""
from __future__ import annotations

import streamlit as st

from .integration_v5 import render_integration_workspace
from .overview_v4 import TIMEFRAME_LABELS
from .overview_v4 import render_unified_overview as _render_v4


def render_unified_overview(symbol: str, interval: str = "1d") -> None:
    _render_v4(symbol, interval)
    st.divider()
    render_integration_workspace(symbol, interval)


__all__ = ["TIMEFRAME_LABELS", "render_unified_overview"]
