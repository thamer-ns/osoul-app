from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

import streamlit as st

from security import logout_user

NAV_ITEMS = [
    ("🏠 الرئيسية", "home"),
    ("🔎 التحليل", "analysis"),
    ("⚡ محفظة المضاربة", "spec"),
    ("💼 محفظة الاستثمار", "invest"),
    ("📜 الصكوك", "sukuk"),
    ("💰 السيولة", "cash"),
    ("🧪 الاختبار الخلفي", "backtest"),
    ("📡 نبض المحفظة", "pulse"),
    ("🚦 الإشارات", "signals"),
    ("➕ إضافة صفقة", "add"),
    ("🛠️ الأدوات", "tools"),
    ("⚙️ الإعدادات", "settings"),
]
_ALLOWED = {key for _, key in NAV_ITEMS} | {"update"}
_LABEL_BY_KEY = {key: label for label, key in NAV_ITEMS}
_KEY_BY_LABEL = {label: key for label, key in NAV_ITEMS}


def _logo_data_uri(path: str = "assets/logo_mark.png") -> str:
    logo_path = Path(path)
    if not logo_path.exists():
        return ""
    try:
        encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception:
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
        pass
    try:
        st.experimental_set_query_params(page=page)
    except Exception:
        pass


def sync_page_from_query_params_once() -> None:
    if st.session_state.get("_synced_page_from_qp_once"):
        return
    st.session_state["_synced_page_from_qp_once"] = True
    requested = _safe_get_query_page()
    if requested:
        st.session_state["page"] = requested


def _go(page: str) -> None:
    destination = page if page in _ALLOWED else "home"
    st.session_state["page"] = destination
    _safe_set_query_page(destination)
    st.rerun()


def _render_sidebar_brand() -> None:
    logo = _logo_data_uri()
    if logo:
        st.sidebar.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:.65rem;margin:.25rem 0 1rem">
              <img src="{logo}" style="width:42px;height:42px;border-radius:12px" />
              <div><strong style="font-size:1.15rem">أصولي</strong><br><small>إدارة وتحليل المحفظة</small></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.title("📈 أصولي")


def render_navbar() -> None:
    """Render one compact navigation surface that works on desktop and mobile."""
    sync_page_from_query_params_once()
    current = str(st.session_state.get("page") or "home")
    if current not in _ALLOWED or current == "update":
        current = "home"
        st.session_state["page"] = current

    _render_sidebar_brand()
    username = str(st.session_state.get("username") or "المستخدم")
    st.sidebar.caption(f"مسجل الدخول: {username}")

    current_label = _LABEL_BY_KEY.get(current, _LABEL_BY_KEY["home"])
    selected_label = st.sidebar.radio(
        "التنقل",
        options=[label for label, _ in NAV_ITEMS],
        index=[label for label, _ in NAV_ITEMS].index(current_label),
        label_visibility="collapsed",
        key="sidebar_navigation",
    )
    selected_key = _KEY_BY_LABEL[selected_label]
    if selected_key != current:
        _go(selected_key)

    st.sidebar.divider()
    if st.sidebar.button(
        "🔄 تحديث أسعار المراكز",
        use_container_width=True,
    ):
        _go("update")

    if st.sidebar.button(
        "🚪 تسجيل الخروج",
        use_container_width=True,
    ):
        logout_user()
        st.cache_data.clear()
        st.rerun()

    st.caption(f"أصولي / {current_label}")
