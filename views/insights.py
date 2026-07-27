from __future__ import annotations

import importlib
import logging
from typing import Any, Optional

import streamlit as st

_SECTION_KEYS = ("analysis", "signals", "backtest")
_SECTION_META = {
    "analysis": {
        "label": "التحليل الشامل",
        "icon": "📊",
        "description": "المالي والفني والكلاسيكي والمستشار والخطة",
        "module": "views.analysis",
        "renderer": "view_analysis",
    },
    "signals": {
        "label": "الإشارات",
        "icon": "🚦",
        "description": "الفرص الحالية والدخول والوقف والأهداف",
        "module": "views.signals",
        "renderer": "view_signals",
    },
    "backtest": {
        "label": "الاختبار الخلفي",
        "icon": "🧪",
        "description": "اختبار الاستراتيجيات على البيانات التاريخية",
        "module": "views.lab",
        "renderer": "view_backtester_ui",
    },
}

_LOGGER = logging.getLogger(__name__)


def _query_section() -> Optional[str]:
    try:
        value = st.query_params.get("section")
        if isinstance(value, list):
            value = value[0] if value else None
    except Exception:
        try:
            params = st.experimental_get_query_params()
            value = params.get("section", [None])
            value = value[0] if isinstance(value, list) else value
        except Exception:
            _LOGGER.debug("Analysis-section query read failed", exc_info=True)
            return None
    normalized = str(value or "").strip().lower()
    return normalized if normalized in _SECTION_KEYS else None


def _set_query_section(section: str) -> None:
    if section not in _SECTION_KEYS:
        return
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
    stored = str(st.session_state.get("insights_section") or "").strip().lower()
    selected = requested or (stored if stored in _SECTION_KEYS else "analysis")
    st.session_state["insights_section"] = selected
    return selected


def _switch_section(section: str) -> None:
    if section not in _SECTION_KEYS:
        section = "analysis"
    st.session_state["insights_section"] = section
    _set_query_section(section)
    st.rerun()


def _inject_hub_css() -> None:
    st.markdown(
        """
        <style>
        .st-key-osoli_analysis_hub {
          direction:rtl !important;
          text-align:right !important;
          margin:.15rem 0 .8rem !important;
        }
        .st-key-osoli_analysis_hub .os-analysis-hub-hero {
          direction:rtl !important;
          display:flex !important;
          align-items:center !important;
          justify-content:space-between !important;
          gap:1rem !important;
          padding:.82rem 1rem !important;
          margin:0 0 .62rem !important;
          border:1px solid var(--os-border-strong,rgba(15,23,42,.16)) !important;
          border-radius:17px !important;
          background:
            linear-gradient(135deg,rgba(36,87,230,.11),rgba(14,143,202,.055)),
            var(--os-surface,#fff) !important;
          box-shadow:0 7px 24px rgba(15,23,42,.05) !important;
        }
        .st-key-osoli_analysis_hub .os-analysis-hub-title {
          color:var(--os-text,#10203a) !important;
          font-size:1.12rem !important;
          font-weight:900 !important;
        }
        .st-key-osoli_analysis_hub .os-analysis-hub-sub {
          color:var(--os-muted,#64748b) !important;
          font-size:.79rem !important;
          font-weight:650 !important;
        }
        .st-key-osoli_analysis_hub [data-testid="stHorizontalBlock"] {
          direction:rtl !important;
          flex-direction:row !important;
          gap:.55rem !important;
        }
        .st-key-osoli_analysis_hub .stButton > button {
          min-height:66px !important;
          border-radius:14px !important;
          padding:.55rem .45rem !important;
          font-size:.84rem !important;
          font-weight:850 !important;
          justify-content:center !important;
          white-space:normal !important;
        }
        .st-key-osoli_analysis_hub .stButton > button p {
          direction:rtl !important;
          text-align:center !important;
          white-space:normal !important;
        }
        @media (max-width:700px) {
          .st-key-osoli_analysis_hub .os-analysis-hub-hero {
            align-items:flex-start !important;
            flex-direction:column !important;
            gap:.18rem !important;
          }
          .st-key-osoli_analysis_hub [data-testid="stHorizontalBlock"] {
            flex-direction:column !important;
          }
          .st-key-osoli_analysis_hub [data-testid="stHorizontalBlock"] > [data-testid="column"] {
            width:100% !important;
            flex:1 1 100% !important;
          }
          .st-key-osoli_analysis_hub .stButton > button {
            min-height:52px !important;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_section_selector(selected: str) -> None:
    columns = st.columns(3, gap="small")
    for column, section in zip(columns, _SECTION_KEYS):
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
    meta = _SECTION_META[section]
    try:
        module = importlib.import_module(str(meta["module"]))
        renderer = getattr(module, str(meta["renderer"]))
        renderer(finance)
    except Exception:
        _LOGGER.exception("Analysis hub section failed: %s", section)
        st.error(f"تعذر تحميل قسم {meta['label']} الآن.")
        st.caption("تم تسجيل التفاصيل لدى الخادم دون عرض بيانات تقنية حساسة.")


def view_insights(finance: Any) -> None:
    """Render one analysis section at a time to avoid eager heavy-tab execution."""
    selected = _resolve_section()
    _inject_hub_css()

    with st.container(key="osoli_analysis_hub"):
        st.markdown(
            """
            <div class="os-analysis-hub-hero">
              <div class="os-analysis-hub-title">🧠 مركز التحليل</div>
              <div class="os-analysis-hub-sub">التحليل والإشارات والاختبار الخلفي تحت صفحة واحدة</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _render_section_selector(selected)
        st.caption(str(_SECTION_META[selected]["description"]))

    _render_active_section(selected, finance)
