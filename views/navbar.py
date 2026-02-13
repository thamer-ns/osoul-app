# views/navbar.py
import streamlit as st

from typing import List, Tuple

from security import logout_user


_NAV_ITEMS: List[Tuple[str, str]] = [
    ("🏠 لوحة التحكم", "home"),
    ("📊 نبض السوق", "pulse"),
    ("📁 المحفظة (مضاربة)", "spec"),
    ("🏦 المحفظة (استثمار)", "invest"),
    ("🕌 الصكوك", "sukuk"),
    ("💵 الكاش", "cash"),
    ("⚡ الإشارات", "signals"),
    ("🧠 التحليل", "analysis"),
    ("🧪 الباكتيست", "backtest"),
    ("➕ إضافة", "add"),
    ("🔄 تحديث الأسعار", "update"),
    ("🧰 أدوات", "tools"),
    ("⚙️ الإعدادات", "settings"),
]


def render_navbar(active_page: str = ""):
    """Render sidebar navigation and keep st.session_state.page in sync."""
    # brand
    try:
        # Inline brand (sidebar)
        import config
        from components import _img_to_base64  # type: ignore

        mark = getattr(config, "LOGO_MARK_PATH", "assets/logo_mark.png")
        b64 = _img_to_base64(mark)
        img = f"<img src=\"data:image/png;base64,{b64}\"/>" if b64 else ""
        st.sidebar.markdown(
            f"""
            <div class='os-sidebar-brand'>
              {img}
              <div style='min-width:0;'>
                <div class='t'>{config.APP_NAME}</div>
                <div class='s'>منصة الذكاء الكمي للأسواق</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    except Exception:
        pass

    labels = [x[0] for x in _NAV_ITEMS]
    keys = [x[1] for x in _NAV_ITEMS]

    # Choose default index
    try:
        idx = keys.index(active_page) if active_page in keys else 0
    except Exception:
        idx = 0

    choice = st.sidebar.radio("التنقل", labels, index=idx, key="__nav_choice")

    page = keys[labels.index(choice)]
    if st.session_state.get("page") != page:
        st.session_state["page"] = page
        st.rerun()

    st.sidebar.markdown("---")

    if st.sidebar.button("تسجيل الخروج", use_container_width=True):
        logout_user()
        # Keep ui_theme but clear the rest
        theme = st.session_state.get("ui_theme")
        st.session_state.clear()
        if theme:
            st.session_state["ui_theme"] = theme
        st.rerun()

