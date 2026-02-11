# feature_flags.py
from __future__ import annotations

from typing import Any, Dict

import streamlit as st

# ============================================================
# 🧪 Feature Flags (اختيارية)
# - الهدف: إضافة ميزات بدون التأثير على المستخدم العادي
# - التخزين: session_state فقط (آمن ولا يغيّر قاعدة البيانات)
# ============================================================

DEFAULT_FLAGS: Dict[str, bool] = {
    # Portfolio analytics
    "enable_xirr": False,

    # Lab / backtester
    "enable_strategy_notes": False,

    # UI wrappers (Arabic placeholders + expander label)
    "use_ar_wrappers": False,

    # Compare engines / legacy
    "enable_engine_compare": False,

    # 🧠 Self-learning (log predictions -> evaluate later -> adapt weights)
    # Safe by design: it does not change calculations, only adds:
    # - logging of signals
    # - evaluation of outcomes after N bars
    # - bounded weight updates for boolean features
    "enable_self_learning": True,
}


def _flags_dict() -> Dict[str, bool]:
    d = st.session_state.get("feature_flags")
    if not isinstance(d, dict):
        d = {}
        st.session_state["feature_flags"] = d
    # ensure defaults
    for k, v in DEFAULT_FLAGS.items():
        if k not in d:
            d[k] = bool(v)
    return d


def get_flag(name: str, default: bool = False) -> bool:
    d = _flags_dict()
    return bool(d.get(name, default))


def set_flag(name: str, value: bool) -> None:
    d = _flags_dict()
    d[name] = bool(value)
    st.session_state["feature_flags"] = d


def get_all_flags() -> Dict[str, bool]:
    return dict(_flags_dict())
