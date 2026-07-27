from __future__ import annotations

import logging
from typing import Optional

import streamlit as st

NAV_ITEMS = [
    ("الرئيسية", "home"),
    ("مركز التحليل", "insights"),
    ("المحافظ", "portfolios"),
    ("إضافة صفقة", "add"),
    ("السيولة", "cash"),
    ("نبض المحفظة", "pulse"),
    ("الأدوات", "tools"),
    ("الإعدادات", "settings"),
]

_ICON_BY_KEY = {
    "home": "🏠",
    "insights": "🧠",
    "portfolios": "💼",
    "add": "➕",
    "cash": "💰",
    "pulse": "📡",
    "tools": "🛠️",
    "settings": "⚙️",
    "update": "🔄",
}

_SHORT_LABEL_BY_KEY = {
    "home": "الرئيسية",
    "insights": "التحليل",
    "portfolios": "المحافظ",
    "add": "إضافة",
    "cash": "السيولة",
    "pulse": "النبض",
    "tools": "الأدوات",
    "settings": "الإعدادات",
}

_HELP_BY_KEY = {
    "home": "العودة إلى لوحة أصولي الرئيسية",
    "insights": "التحليل والإشارات والاختبار الخلفي في مركز واحد",
    "portfolios": "المضاربة والاستثمار والصكوك داخل مركز محافظ واحد",
    "add": "تسجيل صفقة جديدة",
    "cash": "حركة السيولة والإيداعات والسحوبات",
    "pulse": "متابعة أسعار المراكز المفتوحة وتغيرها اليومي",
    "tools": "الأدوات المساعدة",
    "settings": "الإعدادات وتحديث الأسعار وتسجيل الخروج",
}

_NAV_KEYS = tuple(key for _, key in NAV_ITEMS)
_PRIMARY_KEYS = _NAV_KEYS
_SECONDARY_KEYS: tuple[str, ...] = ()
_LEGACY_ANALYSIS_ROUTES = {
    "analysis": "analysis",
    "signals": "signals",
    "backtest": "backtest",
}
_LEGACY_PORTFOLIO_ROUTES = {
    "spec": "spec",
    "invest": "invest",
    "sukuk": "sukuk",
}
_ALLOWED = set(_NAV_KEYS) | {"update"}
_ROUTABLE = (
    _ALLOWED
    | set(_LEGACY_ANALYSIS_ROUTES)
    | set(_LEGACY_PORTFOLIO_ROUTES)
)
_LABEL_BY_KEY = {key: label for label, key in NAV_ITEMS}
_LABEL_BY_KEY["update"] = "تحديث الأسعار"
_LOGGER = logging.getLogger(__name__)


def _safe_get_query_page() -> Optional[str]:
    try:
        value = st.query_params.get("page")
        if isinstance(value, list):
            value = value[0] if value else None
    except Exception:
        try:
            params = st.experimental_get_query_params()
            value = params.get("page", [None])
            value = value[0] if isinstance(value, list) else value
        except Exception:
            _LOGGER.debug("Query parameter read failed", exc_info=True)
            return None
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized if normalized in _ROUTABLE else None


def _clear_section_query_param() -> None:
    try:
        if "section" in st.query_params:
            del st.query_params["section"]
    except Exception:
        _LOGGER.debug("Section query cleanup failed", exc_info=True)


def _safe_set_query_page(page: str) -> None:
    destination = _canonical_page(page)
    try:
        st.query_params["page"] = destination
        if destination not in {"insights", "portfolios"}:
            _clear_section_query_param()
        return
    except Exception:
        _LOGGER.debug("Modern query-param update failed", exc_info=True)
    try:
        st.experimental_set_query_params(page=destination)
    except Exception:
        _LOGGER.debug("Legacy query-param update failed", exc_info=True)


def _canonical_page(value: object) -> str:
    page = str(value or "home").strip().lower()
    if page in _LEGACY_ANALYSIS_ROUTES:
        return "insights"
    if page in _LEGACY_PORTFOLIO_ROUTES:
        return "portfolios"
    return page if page in _ALLOWED else "home"


def _legacy_section(value: object) -> Optional[str]:
    page = str(value or "").strip().lower()
    return _LEGACY_ANALYSIS_ROUTES.get(page)


def _legacy_portfolio_section(value: object) -> Optional[str]:
    page = str(value or "").strip().lower()
    return _LEGACY_PORTFOLIO_ROUTES.get(page)


def sync_page_from_query_params_once() -> None:
    requested = _safe_get_query_page()
    if not requested:
        return
    analysis_section = _legacy_section(requested)
    if analysis_section:
        st.session_state["insights_section"] = analysis_section
    portfolio_section = _legacy_portfolio_section(requested)
    if portfolio_section:
        st.session_state["portfolios_section"] = portfolio_section
    destination = _canonical_page(requested)
    if destination != st.session_state.get("page"):
        st.session_state["page"] = destination
    if requested != destination:
        _safe_set_query_page(destination)


def _validated_page(value: object) -> str:
    return _canonical_page(value)


def _display_page(page: str) -> str:
    canonical = _canonical_page(page)
    return "home" if canonical == "update" else canonical


def navigate_to(page: str, *, rerun: bool = True) -> None:
    analysis_section = _legacy_section(page)
    if analysis_section:
        st.session_state["insights_section"] = analysis_section
    portfolio_section = _legacy_portfolio_section(page)
    if portfolio_section:
        st.session_state["portfolios_section"] = portfolio_section
    destination = _canonical_page(page)
    st.session_state["page"] = destination
    _safe_set_query_page(destination)
    if rerun:
        st.rerun()


def _inject_compact_nav_css() -> None:
    st.markdown(
        """
        <style>
        .st-key-osoli_icon_navigation {
          direction:rtl !important;
          margin:.06rem 0 .5rem !important;
          padding:.3rem .34rem !important;
          border:1px solid var(--os-border-strong,rgba(15,23,42,.16)) !important;
          border-radius:13px !important;
          background:
            linear-gradient(135deg,rgba(36,87,230,.065),rgba(14,143,202,.022)),
            var(--os-surface,#fff) !important;
          box-shadow:0 4px 16px rgba(15,23,42,.04) !important;
          overflow:hidden !important;
        }
        .st-key-osoli_nav_row [data-testid="stHorizontalBlock"] {
          direction:rtl !important;
          display:flex !important;
          flex-direction:row !important;
          flex-wrap:nowrap !important;
          align-items:stretch !important;
          gap:.24rem !important;
          margin:0 !important;
          overflow-x:auto !important;
          overflow-y:hidden !important;
          scrollbar-width:thin !important;
          padding:0 !important;
        }
        .st-key-osoli_nav_row [data-testid="stHorizontalBlock"] > [data-testid="column"] {
          direction:rtl !important;
          width:auto !important;
          min-width:0 !important;
          flex:1 1 0 !important;
        }
        .st-key-osoli_nav_row .stButton > button {
          width:100% !important;
          min-width:0 !important;
          min-height:40px !important;
          height:40px !important;
          padding:.2rem .14rem !important;
          border-radius:9px !important;
          justify-content:center !important;
          gap:.18rem !important;
          font-size:.72rem !important;
          font-weight:850 !important;
          line-height:1.1 !important;
          white-space:nowrap !important;
          box-shadow:none !important;
          overflow:hidden !important;
        }
        .st-key-osoli_nav_row .stButton > button p {
          direction:rtl !important;
          text-align:center !important;
          white-space:nowrap !important;
          overflow:hidden !important;
          text-overflow:ellipsis !important;
          font-size:.72rem !important;
          line-height:1.08 !important;
        }
        .st-key-osoli_nav_row .stButton > button [data-testid="stIconMaterial"] {
          font-size:.88rem !important;
          min-width:.88rem !important;
        }
        @media (max-width:900px) {
          .st-key-osoli_nav_row [data-testid="stHorizontalBlock"] > [data-testid="column"] {
            min-width:86px !important;
            flex:0 0 86px !important;
          }
        }
        @media (max-width:600px) {
          .st-key-osoli_nav_row [data-testid="stHorizontalBlock"] > [data-testid="column"] {
            min-width:78px !important;
            flex:0 0 78px !important;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_navigation_row(current: str) -> None:
    columns = st.columns(len(_NAV_KEYS), gap="small")
    for column, key in zip(columns, _NAV_KEYS):
        column.button(
            _SHORT_LABEL_BY_KEY[key],
            icon=_ICON_BY_KEY[key],
            type="primary" if key == current else "secondary",
            use_container_width=True,
            key=f"nav_icon_{key}",
            help=_HELP_BY_KEY[key],
            on_click=navigate_to,
            args=(key,),
            kwargs={"rerun": False},
        )


def _render_compact_navigation(current: str) -> None:
    _inject_compact_nav_css()
    with st.container(key="osoli_icon_navigation"):
        with st.container(key="osoli_nav_row"):
            _render_navigation_row(current)


def render_navbar() -> None:
    """Render one single-row navigation bar; account actions live in settings."""
    sync_page_from_query_params_once()
    raw_page = st.session_state.get("page")

    analysis_section = _legacy_section(raw_page)
    if analysis_section:
        st.session_state["insights_section"] = analysis_section
    portfolio_section = _legacy_portfolio_section(raw_page)
    if portfolio_section:
        st.session_state["portfolios_section"] = portfolio_section

    route_page = _validated_page(raw_page)
    if route_page != raw_page:
        st.session_state["page"] = route_page
        _safe_set_query_page(route_page)
    _render_compact_navigation(_display_page(route_page))
