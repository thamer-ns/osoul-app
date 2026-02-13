# views/navbar.py
import streamlit as st
from typing import List, Tuple

from security import logout_user

# ✅ لازم تتطابق مع router() في views/__init__.py
_NAV_ITEMS: List[Tuple[str, str]] = [
    ("🏠 لوحة التحكم", "home"),
    ("📊 نبض السوق", "pulse"),
    ("📁 المحفظة (مضاربة)", "spec"),
    ("🏦 المحفظة (استثمار)", "invest"),
    ("🕌 الصكوك", "sukuk"),
    ("💵 الكاش", "cash"),
    ("🧠 التحليل", "analysis"),
    ("🧪 الباكتيست", "backtest"),
    ("➕ إضافة صفقة", "add"),
    ("🧰 أدوات", "tools"),
    ("⚙️ الإعدادات", "settings"),
    ("🔄 تحديث الأسعار", "update"),
]

_ALLOWED = {k for _, k in _NAV_ITEMS}

def _get_qp_page() -> str | None:
    # يدعم st.query_params (الجديد) و st.experimental_get_query_params (القديم)
    try:
        qp = st.query_params  # type: ignore[attr-defined]
        if isinstance(qp, dict):
            v = qp.get("page")
            if isinstance(v, (list, tuple)):
                return v[0] if v else None
            return v
        # QueryParams object behaves like mapping
        v = qp.get("page")
        if isinstance(v, (list, tuple)):
            return v[0] if v else None
        return v
    except Exception:
        try:
            qp = st.experimental_get_query_params()
            v = qp.get("page", [None])[0]
            return v
        except Exception:
            return None

def _set_qp_page(page: str):
    try:
        st.query_params.update(page=page)  # type: ignore[attr-defined]
    except Exception:
        try:
            st.experimental_set_query_params(page=page)
        except Exception:
            pass

def render_navbar():
    """Sidebar navigation (RTL + قابلة للطي)"""
    # ✅ Sync page from query params once
    if "_qp_synced" not in st.session_state:
        st.session_state["_qp_synced"] = True
        qp_page = _get_qp_page()
        if qp_page in _ALLOWED:
            st.session_state["page"] = qp_page

    # ✅ Ensure page exists
    if "page" not in st.session_state or st.session_state.get("page") not in _ALLOWED:
        st.session_state["page"] = "home"

    current = st.session_state.get("page", "home")

    # Brand header (optional)
    try:
        import config
        from components import _img_to_base64  # type: ignore
        mark = getattr(config, "LOGO_MARK_PATH", "assets/logo_mark.png")
        b64 = _img_to_base64(mark)
        img = f"<img src='data:image/png;base64,{b64}' style='width:34px;height:34px;border-radius:10px;'/>" if b64 else ""
        st.sidebar.markdown(
            f"""
            <div class='os-sidebar-brand' style='display:flex;gap:10px;align-items:center;margin:8px 0 14px 0;'>
              {img}
              <div style='min-width:0;'>
                <div style='font-weight:800;font-size:18px;line-height:1.1'>{getattr(config,'APP_NAME','أصولي')}</div>
                <div style='opacity:.75;font-size:12px;line-height:1.2'>منصة الذكاء الكمي للأسواق</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    except Exception:
        pass

    labels = [x[0] for x in _NAV_ITEMS]
    keys = [x[1] for x in _NAV_ITEMS]
    idx = keys.index(current) if current in keys else 0

    # Radio navigation
    choice = st.sidebar.radio(
        "القائمة",
        labels,
        index=idx,
        key="__nav_choice",
    )
    page = keys[labels.index(choice)]

    if page != current:
        st.session_state["page"] = page
        _set_qp_page(page)
        st.rerun()

    st.sidebar.markdown("---")

    # Quick actions
    col1, col2 = st.sidebar.columns(2)
    if col1.button("🏠 الرئيسية", use_container_width=True):
        st.session_state["page"] = "home"
        _set_qp_page("home")
        st.rerun()
    if col2.button("🔄 تحديث", use_container_width=True):
        st.session_state["page"] = "update"
        _set_qp_page("update")
        st.rerun()

    st.sidebar.markdown("---")

    if st.sidebar.button("تسجيل الخروج", use_container_width=True):
        logout_user()
        # Keep theme preference if any
        theme = st.session_state.get("ui_theme")
        st.session_state.clear()
        if theme:
            st.session_state["ui_theme"] = theme
        _set_qp_page("home")
        st.rerun()
