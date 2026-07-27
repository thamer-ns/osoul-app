from __future__ import annotations

import logging
from typing import Optional

import streamlit as st

from security import logout_user

NAV_ITEMS = [
    ("الرئيسية", "home"),
    ("مركز التحليل", "insights"),
    ("محفظة المضاربة", "spec"),
    ("محفظة الاستثمار", "invest"),
    ("إضافة صفقة", "add"),
    ("الصكوك", "sukuk"),
    ("السيولة", "cash"),
    ("نبض المحفظة", "pulse"),
    ("الأدوات", "tools"),
    ("الإعدادات", "settings"),
]

_ICON_BY_KEY = {
    "home": "🏠",
    "insights": "🧠",
    "spec": "⚡",
    "invest": "💼",
    "add": "➕",
    "sukuk": "📜",
    "cash": "💰",
    "pulse": "📡",
    "tools": "🛠️",
    "settings": "⚙️",
    "update": "🔄",
}

_SHORT_LABEL_BY_KEY = {
    "home": "الرئيسية",
    "insights": "التحليل",
    "spec": "المضاربة",
    "invest": "الاستثمار",
    "add": "إضافة",
    "sukuk": "الصكوك",
    "cash": "السيولة",
    "pulse": "النبض",
    "tools": "الأدوات",
    "settings": "الإعدادات",
}

_HELP_BY_KEY = {
    "home": "العودة إلى لوحة أصولي الرئيسية",
    "insights": "التحليل والإشارات والاختبار الخلفي في مركز واحد",
    "spec": "إدارة محفظة المضاربة",
    "invest": "إدارة محفظة الاستثمار",
    "add": "تسجيل صفقة جديدة",
    "sukuk": "إدارة الصكوك والدخل الثابت",
    "cash": "حركة السيولة والإيداعات والسحوبات",
    "pulse": "متابعة نبض المحفظة والتنبيهات",
    "tools": "الأدوات المساعدة",
    "settings": "إعدادات التطبيق والحساب",
}

_NAV_KEYS = tuple(key for _, key in NAV_ITEMS)
_PRIMARY_KEYS = _NAV_KEYS
_SECONDARY_KEYS: tuple[str, ...] = ()
_LEGACY_ANALYSIS_ROUTES = {
    "analysis": "analysis",
    "signals": "signals",
    "backtest": "backtest",
}
_ALLOWED = set(_NAV_KEYS) | {"update"}
_ROUTABLE = _ALLOWED | set(_LEGACY_ANALYSIS_ROUTES)
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
        if destination != "insights":
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
    return page if page in _ALLOWED else "home"


def _legacy_section(value: object) -> Optional[str]:
    page = str(value or "").strip().lower()
    return _LEGACY_ANALYSIS_ROUTES.get(page)


def sync_page_from_query_params_once() -> None:
    requested = _safe_get_query_page()
    if not requested:
        return
    legacy_section = _legacy_section(requested)
    if legacy_section:
        st.session_state["insights_section"] = legacy_section
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
    legacy_section = _legacy_section(page)
    if legacy_section:
        st.session_state["insights_section"] = legacy_section
    destination = _canonical_page(page)
    st.session_state["page"] = destination
    _safe_set_query_page(destination)
    if rerun:
        st.rerun()


def _logout_callback() -> None:
    logout_user()
    st.cache_data.clear()


def _inject_compact_nav_css() -> None:
    st.markdown(
        """
        <style>
        .st-key-osoli_icon_navigation {
          direction:rtl !important;
          margin:.08rem 0 .5rem !important;
          padding:.34rem .4rem .38rem !important;
          border:1px solid var(--os-border-strong,rgba(15,23,42,.16)) !important;
          border-radius:14px !important;
          background:
            linear-gradient(135deg,rgba(36,87,230,.07),rgba(14,143,202,.025)),
            var(--os-surface,#fff) !important;
          box-shadow:0 5px 18px rgba(15,23,42,.045) !important;
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
          padding:.04rem 0 .16rem !important;
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
          min-height:42px !important;
          height:42px !important;
          padding:.22rem .12rem !important;
          border-radius:10px !important;
          justify-content:center !important;
          gap:.18rem !important;
          font-size:.66rem !important;
          font-weight:850 !important;
          line-height:1.15 !important;
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
          font-size:.66rem !important;
          line-height:1.1 !important;
        }
        .st-key-osoli_nav_row .stButton > button [data-testid="stIconMaterial"] {
          font-size:.9rem !important;
          min-width:.9rem !important;
        }
        .st-key-osoli_nav_actions {
          margin-top:.22rem !important;
          padding-top:.24rem !important;
          border-top:1px solid var(--os-border,rgba(15,23,42,.1)) !important;
        }
        .st-key-osoli_nav_actions [data-testid="stHorizontalBlock"] {
          direction:rtl !important;
          flex-direction:row !important;
          align-items:center !important;
          gap:.32rem !important;
        }
        .st-key-osoli_nav_actions .stButton > button {
          min-height:32px !important;
          height:32px !important;
          padding:.15rem .45rem !important;
          border-radius:9px !important;
          font-size:.68rem !important;
          white-space:nowrap !important;
        }
        .st-key-osoli_nav-current {
          color:var(--os-muted,#64748b) !important;
          font-size:.7rem !important;
          font-weight:700 !important;
          padding:.2rem .15rem !important;
          white-space:nowrap !important;
          overflow:hidden !important;
          text-overflow:ellipsis !important;
        }
        @media (max-width:1100px) {
          .st-key-osoli_nav_row [data-testid="stHorizontalBlock"] > [data-testid="column"] {
            min-width:82px !important;
            flex:0 0 82px !important;
          }
          .st-key-osoli_nav_row .stButton > button,
          .st-key-osoli_nav_row .stButton > button p {
            font-size:.62rem !important;
          }
        }
        @media (max-width:600px) {
          .st-key-osoli_icon_navigation {
            padding:.28rem !important;
            border-radius:12px !important;
          }
          .st-key-osoli_nav_row [data-testid="stHorizontalBlock"] > [data-testid="column"] {
            min-width:76px !important;
            flex:0 0 76px !important;
          }
          .st-key-osoli_nav_row .stButton > button {
            min-height:39px !important;
            height:39px !important;
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
        with st.container(key="osoli_nav_actions"):
            current_col, refresh_col, logout_col = st.columns([8, 1, 1], gap="small")
            current_col.markdown(
                f'<div class="st-key-osoli_nav-current">{_ICON_BY_KEY.get(current, "🏠")} '
                f'{_LABEL_BY_KEY.get(current, "الرئيسية")}</div>',
                unsafe_allow_html=True,
            )
            refresh_col.button(
                "تحديث",
                icon="🔄",
                use_container_width=True,
                key="nav_refresh",
                help="تحديث أسعار جميع المراكز عند الطلب",
                on_click=navigate_to,
                args=("update",),
                kwargs={"rerun": False},
            )
            logout_col.button(
                "خروج",
                icon="🚪",
                use_container_width=True,
                key="nav_logout",
                help="الخروج الآمن من الحساب",
                on_click=_logout_callback,
            )


def render_navbar() -> None:
    """Render one compact horizontal navigation row without a sidebar."""
    sync_page_from_query_params_once()
    raw_page = st.session_state.get("page")
    legacy_section = _legacy_section(raw_page)
    if legacy_section:
        st.session_state["insights_section"] = legacy_section
    route_page = _validated_page(raw_page)
    if route_page != raw_page:
        st.session_state["page"] = route_page
        _safe_set_query_page(route_page)
    _render_compact_navigation(_display_page(route_page))
