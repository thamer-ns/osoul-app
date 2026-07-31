from __future__ import annotations

import importlib
import logging
from typing import Any

import streamlit as st

# The analysis area intentionally has only two user-facing destinations.
_SECTION_KEYS = ("analysis", "evaluation")
_LEGACY_SECTION_REDIRECTS = {
    "signals": "analysis",
    "backtest": "evaluation",
}
_SECTION_META = {
    "analysis": {
        "label": "التحليل الشامل",
        "icon": "📊",
        "description": (
            "اتجاه صاعد أو هابط، دخول ووقف وأهداف، ثم رأي مستشار عملي "
            "داخل شاشة واحدة"
        ),
        "module": "views.analysis_fast",
        "renderer": "view_analysis",
    },
    "evaluation": {
        "label": "التدقيق",
        "icon": "🎯",
        "description": (
            "تدقيق النتائج والمعايرة وسلامة السجل دون تغيير القواعد تلقائيًا"
        ),
        "module": "views.analysis.evaluation",
        "renderer": "render_evaluation_center",
    },
}

_LOGGER = logging.getLogger(__name__)


def _normalize_section(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    normalized = _LEGACY_SECTION_REDIRECTS.get(normalized, normalized)
    return normalized if normalized in _SECTION_KEYS else None


def _query_section() -> str | None:
    try:
        value = st.query_params.get("section")
        if isinstance(value, list):
            value = value[0] if value else None
        return _normalize_section(value)
    except Exception:
        _LOGGER.debug("Modern analysis-section query read failed", exc_info=True)
    try:
        params = st.experimental_get_query_params()
        value = params.get("section", [None])
        value = value[0] if isinstance(value, list) else value
        return _normalize_section(value)
    except Exception:
        _LOGGER.debug("Legacy analysis-section query read failed", exc_info=True)
        return None


def _set_query_section(section: str) -> None:
    section = _normalize_section(section) or "analysis"
    try:
        st.query_params["page"] = "insights"
        st.query_params["section"] = section
        return
    except Exception:
        _LOGGER.debug("Modern analysis-section query update failed", exc_info=True)
    try:
        st.experimental_set_query_params(page="insights", section=section)
    except Exception:
        _LOGGER.debug("Legacy analysis-section query update failed", exc_info=True)


def _resolve_section() -> str:
    requested = _query_section()
    stored = _normalize_section(st.session_state.get("insights_section"))
    selected = requested or stored or "analysis"
    st.session_state["insights_section"] = selected
    return selected


def _switch_section(section: str) -> None:
    selected = _normalize_section(section) or "analysis"
    st.session_state["insights_section"] = selected
    _set_query_section(selected)
    st.rerun()


def _render_section_selector(selected: str) -> None:
    columns = st.columns(2, gap="small")
    for column, section in zip(columns, _SECTION_KEYS, strict=True):
        meta = _SECTION_META[section]
        if column.button(
            meta["label"],
            icon=meta["icon"],
            type="primary" if section == selected else "secondary",
            use_container_width=True,
            key=f"analysis_hub_section_{section}",
            help=meta["description"],
        ):
            _switch_section(section)


def _render_active_section(section: str, finance: Any) -> None:
    selected = _normalize_section(section) or "analysis"
    meta = _SECTION_META[selected]
    try:
        module = importlib.import_module(str(meta["module"]))
        renderer = getattr(module, str(meta["renderer"]))
        if not callable(renderer):
            raise TypeError("analysis renderer is not callable")
        renderer(finance)
    except Exception:
        _LOGGER.exception("Analysis hub section failed: %s", selected)
        st.error(f"تعذر تحميل قسم {meta['label']} الآن.")
        st.caption(f"رمز التشخيص: insights_{selected}")


def view_insights(finance: Any) -> None:
    """Render exactly one of the two supported analysis destinations."""
    selected = _resolve_section()

    st.markdown("## 🧠 مركز التحليل والقرار")
    st.caption(
        "مساران فقط: التحليل الشامل لاتخاذ القرار، والتدقيق لقياس النتائج "
        "وسلامة السجل."
    )
    _render_section_selector(selected)
    st.caption(str(_SECTION_META[selected]["description"]))
    st.divider()
    _render_active_section(selected, finance)


__all__ = ["view_insights"]
