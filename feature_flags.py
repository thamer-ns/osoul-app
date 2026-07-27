"""Compatibility registry for capabilities that are now part of the core product.

These options used to be exposed as experimental session-only switches.  That
made the interface confusing and could silently disable useful behaviour after
one click.  The useful capabilities are now always enabled; obsolete switches
were removed.  The small API remains only for backward-compatible imports.
"""
from __future__ import annotations

from typing import Dict

import streamlit as st

CORE_CAPABILITIES: Dict[str, bool] = {
    # Strategy guidance and previous backtest runs are part of the lab.
    "enable_strategy_notes": True,
    # Arabic-aware controls are part of the global RTL interface.
    "use_ar_wrappers": True,
    # Signal logging is required for outcome evaluation and bounded learning.
    "enable_self_learning": True,
}

_REMOVED_FLAGS = {
    "enable_xirr",
    "enable_engine_compare",
}


def _flags_dict() -> Dict[str, bool]:
    """Return a clean compatibility snapshot with core features forced on."""
    current = st.session_state.get("feature_flags")
    data = dict(current) if isinstance(current, dict) else {}
    for name in _REMOVED_FLAGS:
        data.pop(name, None)
    data.update(CORE_CAPABILITIES)
    st.session_state["feature_flags"] = data
    return data


def get_flag(name: str, default: bool = False) -> bool:
    if name in CORE_CAPABILITIES:
        return True
    if name in _REMOVED_FLAGS:
        return False
    return bool(_flags_dict().get(name, default))


def set_flag(name: str, value: bool) -> None:
    """Retain compatibility without allowing core capabilities to be disabled."""
    data = _flags_dict()
    if name in CORE_CAPABILITIES:
        data[name] = True
    elif name not in _REMOVED_FLAGS:
        data[name] = bool(value)
    st.session_state["feature_flags"] = data


def get_all_flags() -> Dict[str, bool]:
    return dict(_flags_dict())
