from __future__ import annotations

import base64
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

import streamlit as st

from security import logout_user

NAV_ITEMS = [
    ("الرئيسية", "home"),
    ("التحليل", "analysis"),
    ("محفظة المضاربة", "spec"),
    ("محفظة الاستثمار", "invest"),
    ("الصكوك", "sukuk"),
    ("السيولة", "cash"),
    ("الاختبار الخلفي", "backtest"),
    ("نبض المحفظة", "pulse"),
    ("الإشارات", "signals"),
    ("إضافة صفقة", "add"),
    ("الأدوات", "tools"),
    ("الإعدادات", "settings"),
]

_ICON_BY_KEY = {
    "home": "🏠",
    "analysis": "📊",
    "spec": "⚡",
    "invest": "💼",
    "sukuk": "📜",
    "cash": "💰",
    "backtest": "🧪",
    "pulse": "📡",
    "signals": "🚦",
    "add": "➕",
    "tools": "🛠️",
    "settings": "⚙️",
    "update": "🔄",
}

_SHORT_LABEL_BY_KEY = {
    "home": "الرئيسية",
    "analysis": "التحليل",
    "spec": "المضاربة",
    "invest": "الاستثمار",
    "sukuk": "الصكوك",
    "cash": "السيولة",
    "backtest": "اختبار خلفي",
    "pulse": "نبض المحفظة",
    "signals": "الإشارات",
    "add": "إضافة صفقة",
    "tools": "الأدوات",
    "settings": "الإعدادات",
}

_HELP_BY_KEY = {
    "home": "العودة إلى لوحة أصولي الرئيسية",
    "analysis": "التحليل الفني والمالي",
    "spec": "إدارة محفظة المضاربة",
    "invest": "إدارة محفظة الاستثمار",
    "sukuk": "إدارة الصكوك والدخل الثابت",
    "cash": "حركة السيولة والإيداعات والسحوبات",
    "backtest": "اختبار الاستراتيجيات تاريخيًا",
    "pulse": "متابعة نبض المحفظة والتنبيهات",
    "signals": "الإشارات والفرص الحالية",
    "add": "تسجيل صفقة جديدة",
    "tools": "الأدوات المساعدة",
    "settings": "إعدادات التطبيق والحساب",
}

_PRIMARY_KEYS = ("home", "analysis", "spec", "invest", "signals", "add")
_SECONDARY_KEYS = ("sukuk", "cash", "backtest", "pulse", "tools", "settings")
_NAV_KEYS = _PRIMARY_KEYS + _SECONDARY_KEYS
_ALLOWED = set(_NAV_KEYS) | {"update"}
_LABEL_BY_KEY = {key: label for label, key in NAV_ITEMS}
_LABEL_BY_KEY["update"] = "تحديث الأسعار"

_LOGGER = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def _logo_data_uri(path: str = "assets/logo_mark.png") -> str:
    logo_path = Path(path)
    if not logo_path.exists():
        return ""
    try:
        encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        _LOGGER.debug("Logo encoding failed", exc_info=True)
        return ""


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
            return None
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized if normalized in _ALLOWED else None


def _safe_set_query_page(page: str) -> None:
    try:
        st.query_params["page"] = page
        return
    except Exception:
        _LOGGER.debug("Modern query-param update failed", exc_info=True)
    try:
        st.experimental_set_query_params(page=page)
    except Exception:
        _LOGGER.debug("Legacy query-param update failed", exc_info=True)


def sync_page_from_query_params_once() -> None:
    """Synchronise deep links and browser back/forward navigation.

    The historical function name is kept for compatibility, but the check is
    intentionally lightweight on every rerun so changing ``?page=`` after login
    is reflected immediately.
    """
    requested = _safe_get_query_page()
    if requested and requested != st.session_state.get("page"):
        st.session_state["page"] = requested


def _validated_page(value: object) -> str:
    page = str(value or "home").strip().lower()
    return page if page in _ALLOWED else "home"


def _display_page(page: str) -> str:
    """Return the page highlighted in navigation.

    ``update`` is a transient route, so the home tile remains highlighted while
    prices refresh without rewriting the router state.
    """
    return page if page in _LABEL_BY_KEY and page != "update" else "home"


def _go(page: str) -> None:
    destination = _validated_page(page)
    st.session_state["page"] = destination
    _safe_set_query_page(destination)
    st.rerun()


def _logout() -> None:
    logout_user()
    st.cache_data.clear()
    st.rerun()


def _inject_icon_nav_css() -> None:
    st.markdown(
        """
        <style>
        .st-key-osoli_icon_navigation {
          margin:.15rem 0 .8rem !important;
          padding:.72rem .78rem .78rem !important;
          border:1px solid var(--os-border-strong,rgba(15,23,42,.16)) !important;
          border-radius:18px !important;
          background:
            linear-gradient(135deg,rgba(36,87,230,.075),rgba(14,143,202,.035)),
            var(--os-surface,#fff) !important;
          box-shadow:0 8px 26px rgba(15,23,42,.06) !important;
        }
        .st-key-osoli_icon_navigation .os-nav-heading {
          display:flex !important;
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
          gap:.48rem !important;
          margin-bottom:.38rem !important;
        }
        .st-key-osoli_icon_navigation .stButton > button {
          width:100% !important;
          min-height:58px !important;
          padding:.48rem .38rem !important;
          border-radius:14px !important;
          justify-content:center !important;
          font-size:.82rem !important;
          font-weight:850 !important;
          line-height:1.35 !important;
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
          white-space:normal !important;
          text-align:center !important;
        }
        @media (max-width:900px) {
          .st-key-osoli_icon_navigation {
            padding:.58rem !important;
            border-radius:15px !important;
          }
          .st-key-osoli_icon_navigation .stButton > button {
            min-height:52px !important;
            padding:.38rem .2rem !important;
            font-size:.72rem !important;
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
        @media (max-width:560px) {
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
        label = _SHORT_LABEL_BY_KEY[key]
        icon = _ICON_BY_KEY[key]
        active = key == current
        if column.button(
            label,
            icon=icon,
            type="primary" if active else "secondary",
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
              <span>اختر القسم مباشرة — زر الرئيسية ظاهر دائمًا</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.container(key="osoli_nav_primary"):
            _render_navigation_row(_PRIMARY_KEYS, current, "primary")
        with st.container(key="osoli_nav_secondary"):
            _render_navigation_row(_SECONDARY_KEYS, current, "secondary")

        st.caption(
            f"الموقع الحالي: {_ICON_BY_KEY.get(current, '🏠')} "
            f"{_LABEL_BY_KEY.get(current, _LABEL_BY_KEY['home'])}"
        )
        refresh_col, logout_col = st.columns(2, gap="small")
        if refresh_col.button(
            "تحديث",
            icon=_ICON_BY_KEY["update"],
            use_container_width=True,
            key="nav_icon_refresh",
            help="تحديث أسعار جميع المراكز",
        ):
            _go("update")
        if logout_col.button(
            "خروج",
            icon="🚪",
            use_container_width=True,
            key="nav_icon_logout",
            help="تسجيل الخروج من الحساب",
        ):
            _logout()


def _render_sidebar_brand() -> None:
    logo = _logo_data_uri()
    if logo:
        st.sidebar.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:.65rem;margin:.25rem 0 1rem">
              <img src="{logo}" style="width:42px;height:42px;border-radius:12px" />
              <div><strong style="font-size:1.15rem">أصولي</strong><br>
              <small>إدارة وتحليل المحفظة</small></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.title("📈 أصولي")


def _render_sidebar_navigation(current: str) -> None:
    _render_sidebar_brand()
    username = str(st.session_state.get("username") or "المستخدم")
    st.sidebar.caption(f"مسجل الدخول: {username}")

    for key in _NAV_KEYS:
        if st.sidebar.button(
            _LABEL_BY_KEY[key],
            icon=_ICON_BY_KEY[key],
            type="primary" if key == current else "secondary",
            use_container_width=True,
            key=f"sidebar_nav_{key}",
            help=_HELP_BY_KEY[key],
        ):
            _go(key)

    st.sidebar.divider()
    if st.sidebar.button(
        "تحديث أسعار المراكز",
        icon=_ICON_BY_KEY["update"],
        use_container_width=True,
        key="sidebar_refresh_prices",
    ):
        _go("update")

    if st.sidebar.button(
        "تسجيل الخروج",
        icon="🚪",
        use_container_width=True,
        key="sidebar_logout",
    ):
        _logout()


def render_navbar() -> None:
    """Render an always-visible icon menu plus an optional sidebar menu."""
    sync_page_from_query_params_once()

    route_page = _validated_page(st.session_state.get("page"))
    if route_page != st.session_state.get("page"):
        st.session_state["page"] = route_page

    current = _display_page(route_page)

    # Render the in-page menu before the sidebar so it remains usable even when
    # Streamlit's sidebar is collapsed or its toggle is outside the viewport.
    _render_icon_navigation(current)
    _render_sidebar_navigation(current)

    breadcrumb_page = route_page if route_page in _LABEL_BY_KEY else current
    st.caption(
        f"أصولي / {_ICON_BY_KEY.get(breadcrumb_page, '🏠')} "
        f"{_LABEL_BY_KEY.get(breadcrumb_page, _LABEL_BY_KEY['home'])}"
    )
