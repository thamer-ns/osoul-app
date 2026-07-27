from __future__ import annotations

import importlib
import logging
from typing import Any, Optional

import streamlit as st

_SECTION_KEYS = ("spec", "invest", "sukuk")
_SECTION_META = {
    "spec": {
        "label": "محفظة المضاربة",
        "icon": "⚡",
        "description": "الصفقات القصيرة والمتوسطة، المراكز القائمة، الأرشيف وإدارة البيع",
        "module": "views.fast_portfolio",
        "renderer": "view_portfolio",
        "args": ("spec",),
    },
    "invest": {
        "label": "محفظة الاستثمار",
        "icon": "📈",
        "description": "المراكز الاستثمارية طويلة الأجل، الأداء، المخاطر والأرشيف",
        "module": "views.fast_portfolio",
        "renderer": "view_portfolio",
        "args": ("invest",),
    },
    "sukuk": {
        "label": "محفظة الصكوك",
        "icon": "📜",
        "description": "الصكوك القائمة، التوزيعات، مدة الاحتفاظ والتصفية",
        "module": "views.sukuk",
        "renderer": "view_sukuk_portfolio",
        "args": (),
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
            _LOGGER.debug("Portfolio-section query read failed", exc_info=True)
            return None
    normalized = str(value or "").strip().lower()
    return normalized if normalized in _SECTION_KEYS else None


def _set_query_section(section: str) -> None:
    if section not in _SECTION_KEYS:
        return
    try:
        st.query_params["page"] = "portfolios"
        st.query_params["section"] = section
        return
    except Exception:
        _LOGGER.debug("Modern portfolio-section query update failed", exc_info=True)
    try:
        st.experimental_set_query_params(page="portfolios", section=section)
    except Exception:
        _LOGGER.debug("Legacy portfolio-section query update failed", exc_info=True)


def _resolve_section() -> str:
    requested = _query_section()
    stored = str(st.session_state.get("portfolios_section") or "").strip().lower()
    selected = requested or (stored if stored in _SECTION_KEYS else "spec")
    st.session_state["portfolios_section"] = selected
    return selected


def _switch_section(section: str) -> None:
    if section not in _SECTION_KEYS:
        section = "spec"
    st.session_state["portfolios_section"] = section
    _set_query_section(section)
    st.rerun()


def _inject_hub_css() -> None:
    st.markdown(
        """
        <style>
        .st-key-osoli_portfolios_hub {
          direction:rtl !important;
          text-align:right !important;
          margin:.15rem 0 .8rem !important;
        }
        .st-key-osoli_portfolios_hub .os-portfolios-hub-hero {
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
            linear-gradient(135deg,rgba(16,185,129,.10),rgba(36,87,230,.06)),
            var(--os-surface,#fff) !important;
          box-shadow:0 7px 24px rgba(15,23,42,.05) !important;
        }
        .st-key-osoli_portfolios_hub .os-portfolios-hub-title {
          color:var(--os-text,#10203a) !important;
          font-size:1.12rem !important;
          font-weight:900 !important;
        }
        .st-key-osoli_portfolios_hub .os-portfolios-hub-sub {
          color:var(--os-muted,#64748b) !important;
          font-size:.79rem !important;
          font-weight:650 !important;
        }
        .st-key-osoli_portfolios_hub [data-testid="stHorizontalBlock"] {
          direction:rtl !important;
          flex-direction:row !important;
          gap:.55rem !important;
        }
        .st-key-osoli_portfolios_hub .stButton > button {
          min-height:66px !important;
          border-radius:14px !important;
          padding:.55rem .45rem !important;
          font-size:.84rem !important;
          font-weight:850 !important;
          justify-content:center !important;
          white-space:normal !important;
        }
        .st-key-osoli_portfolios_hub .stButton > button p {
          direction:rtl !important;
          text-align:center !important;
          white-space:normal !important;
        }
        @media (max-width:700px) {
          .st-key-osoli_portfolios_hub .os-portfolios-hub-hero {
            align-items:flex-start !important;
            flex-direction:column !important;
            gap:.18rem !important;
          }
          .st-key-osoli_portfolios_hub [data-testid="stHorizontalBlock"] {
            flex-direction:column !important;
          }
          .st-key-osoli_portfolios_hub [data-testid="stHorizontalBlock"] > [data-testid="column"] {
            width:100% !important;
            flex:1 1 100% !important;
          }
          .st-key-osoli_portfolios_hub .stButton > button {
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
            key=f"portfolios_hub_section_{section}",
            help=meta["description"],
        ):
            _switch_section(section)


def _render_active_section(section: str, finance: Any) -> None:
    meta = _SECTION_META[section]
    try:
        module = importlib.import_module(str(meta["module"]))
        renderer = getattr(module, str(meta["renderer"]))
        renderer(finance, *tuple(meta.get("args") or ()))
    except Exception:
        _LOGGER.exception("Portfolio hub section failed: %s", section)
        st.error(f"تعذر تحميل قسم {meta['label']} الآن.")
        st.caption("تم تسجيل التفاصيل لدى الخادم دون عرض بيانات تقنية حساسة.")


def view_portfolios(finance: Any) -> None:
    """Render one portfolio type at a time to keep navigation fast."""
    selected = _resolve_section()
    _inject_hub_css()

    with st.container(key="osoli_portfolios_hub"):
        st.markdown(
            """
            <div class="os-portfolios-hub-hero">
              <div class="os-portfolios-hub-title">💼 المحافظ</div>
              <div class="os-portfolios-hub-sub">المضاربة والاستثمار والصكوك داخل مركز واحد</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _render_section_selector(selected)
        st.caption(str(_SECTION_META[selected]["description"]))

    _render_active_section(selected, finance)
