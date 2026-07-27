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
    "insights": "مركز التحليل",
    "spec": "المضاربة",
    "invest": "الاستثمار",
    "add": "إضافة صفقة",
    "sukuk": "الصكوك",
    "cash": "السيولة",
    "pulse": "نبض المحفظة",
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

_PRIMARY_KEYS = ("home", "insights", "spec", "invest", "add")
_SECONDARY_KEYS = ("sukuk", "cash", "pulse", "tools", "settings")
_NAV_KEYS = _PRIMARY_KEYS + _SECONDARY_KEYS
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
    """Synchronise deep links and browser back/forward navigation safely."""
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
    """Return the page highlighted in the visible navigation."""
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


def _go(page: str) -> None:
    navigate_to(page)


def _logout() -> None:
    logout_user()
    st.cache_data.clear()
    st.rerun()


def _inject_icon_nav_css() -> None:
    st.markdown(
        """
        <style>
        .st-key-osoli_icon_navigation {
          direction:rtl !important;
          text-align:right !important;
          margin:.12rem 0 .82rem !important;
          padding:.72rem .78rem .78rem !important;
          border:1px solid var(--os-border-strong,rgba(15,23,42,.16)) !important;
          border-radius:18px !important;
          background:
            linear-gradient(135deg,rgba(36,87,230,.075),rgba(14,143,202,.035)),
            var(--os-surface,#fff) !important;
          box-shadow:0 8px 26px rgba(15,23,42,.055) !important;
        }
        .st-key-osoli_icon_navigation .os-nav-heading {
          display:flex !important;
          direction:rtl !important;
          align-items:center !important;
          justify-content:space-between !important;
          gap:.75rem !important;
          margin:0 .12rem .52rem !important;
          color:var(--os-text,#10203a) !important;
        }
        .st-key-osoli_icon_navigation .os-nav-heading strong {
          font-size:.98rem !important;
          font-weight:900 !important;
        }
        .st-key-osoli_icon_navigation .os-nav-heading span {
          color:var(--os-muted,#64748b) !important;
          font-size:.76rem !important;
          font-weight:650 !important;
        }
        .st-key-osoli_icon_navigation [data-testid="stHorizontalBlock"] {
          direction:rtl !important;
          flex-direction:row !important;
          gap:.48rem !important;
          margin-bottom:.38rem !important;
        }
        .st-key-osoli_icon_navigation .stButton > button {
          width:100% !important;
          min-height:64px !important;
          padding:.52rem .34rem !important;
          border-radius:14px !important;
          justify-content:center !important;
          font-size:.82rem !important;
          font-weight:850 !important;
          line-height:1.3 !important;
          white-space:normal !important;
          box-shadow:0 3px 12px rgba(15,23,42,.035) !important;
          transition:
            transform .15s ease,
            border-color .15s ease,
            box-shadow .15s ease,
            filter .15s ease !important;
        }
        .st-key-osoli_icon_navigation .stButton > button:hover {
          transform:translateY(-2px) !important;
          border-color:rgba(36,87,230,.28) !important;
          box-shadow:0 8px 18px rgba(36,87,230,.10) !important;
        }
        .st-key-osoli_icon_navigation .stButton > button p {
          direction:rtl !important;
          white-space:normal !important;
          text-align:center !important;
          line-height:1.35 !important;
        }
        .st-key-osoli_icon_navigation .stButton > button [data-testid="stIconMaterial"] {
          font-size:1.12rem !important;
        }
        .st-key-osoli_nav_actions .stButton > button {
          min-height:43px !important;
          font-size:.8rem !important;
        }
        @media (max-width:1000px) {
          .st-key-osoli_icon_navigation {
            padding:.6rem !important;
            border-radius:15px !important;
          }
          .st-key-osoli_icon_navigation .stButton > button {
            min-height:57px !important;
            padding:.4rem .22rem !important;
            font-size:.74rem !important;
          }
          .st-key-osoli_icon_navigation .os-nav-heading span {
            display:none !important;
          }
          .st-key-osoli_nav_primary [data-testid="stHorizontalBlock"],
          .st-key-osoli_nav_secondary [data-testid="stHorizontalBlock"] {
            flex-direction:row !important;
            flex-wrap:wrap !important;
            gap:.42rem !important;
          }
          .st-key-osoli_nav_primary [data-testid="stHorizontalBlock"] > [data-testid="column"],
          .st-key-osoli_nav_secondary [data-testid="stHorizontalBlock"] > [data-testid="column"] {
            width:calc(33.333% - .42rem) !important;
            flex:1 1 calc(33.333% - .42rem) !important;
          }
        }
        @media (max-width:600px) {
          .st-key-osoli_icon_navigation .stButton > button {
            min-height:54px !important;
            font-size:.72rem !important;
          }
          .st-key-osoli_nav_primary [data-testid="stHorizontalBlock"] > [data-testid="column"],
          .st-key-osoli_nav_secondary [data-testid="stHorizontalBlock"] > [data-testid="column"] {
            width:calc(50% - .42rem) !important;
            flex:1 1 calc(50% - .42rem) !important;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_navigation_row(keys: tuple[str, ...], current: str, row: str) -> None:
    columns = st.columns(len(keys), gap="small")
    for column, key in zip(columns, keys):
        if column.button(
            _SHORT_LABEL_BY_KEY[key],
            icon=_ICON_BY_KEY[key],
            type="primary" if key == current else "secondary",
            use_container_width=True,
            key=f"nav_icon_{row}_{key}",
            help=_HELP_BY_KEY[key],
        ):
            _go(key)


def _render_icon_navigation(current: str) -> None:
    _inject_icon_nav_css()
    with st.container(key="osoli_icon_navigation"):
        st.markdown(
            """
            <div class="os-nav-heading">
              <strong>🧭 القائمة الرئيسية</strong>
              <span>تنقل مباشر وواضح دون شريط جانبي</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.container(key="osoli_nav_primary"):
            _render_navigation_row(_PRIMARY_KEYS, current, "primary")
        with st.container(key="osoli_nav_secondary"):
            _render_navigation_row(_SECONDARY_KEYS, current, "secondary")

        with st.container(key="osoli_nav_actions"):
            refresh_col, logout_col = st.columns(2, gap="small")
            if refresh_col.button(
                "تحديث الأسعار",
                icon=_ICON_BY_KEY["update"],
                use_container_width=True,
                key="nav_icon_refresh",
                help="تحديث أسعار جميع المراكز",
            ):
                _go("update")
            if logout_col.button(
                "تسجيل الخروج",
                icon="🚪",
                use_container_width=True,
                key="nav_icon_logout",
                help="الخروج الآمن من الحساب",
            ):
                _logout()


def render_navbar() -> None:
    """Render the only navigation surface; the Streamlit sidebar is disabled."""
    sync_page_from_query_params_once()

    raw_page = st.session_state.get("page")
    legacy_section = _legacy_section(raw_page)
    if legacy_section:
        st.session_state["insights_section"] = legacy_section

    route_page = _validated_page(raw_page)
    if route_page != raw_page:
        st.session_state["page"] = route_page
        _safe_set_query_page(route_page)

    current = _display_page(route_page)
    _render_icon_navigation(current)

    breadcrumb_page = route_page if route_page in _LABEL_BY_KEY else current
    st.caption(
        f"أصولي / {_ICON_BY_KEY.get(breadcrumb_page, '🏠')} "
        f"{_LABEL_BY_KEY.get(breadcrumb_page, _LABEL_BY_KEY['home'])}"
    )
