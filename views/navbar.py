#views/navbar.py
import streamlit as st

def render_navbar():
    buttons = [
        ("🏠 الرئيسية", "home"),
        ("⚡ مضاربة", "spec"),
        ("💎 استثمار", "invest"),
        ("💓 نبض", "pulse"),
        ("📜 صكوك", "sukuk"),
        ("🔍 تحليل", "analysis"),
        ("🧪 المختبر", "backtest"),
        ("💰 السيولة", "cash"),
        ("🔄 تحديث", "update"),
    ]

    st.markdown(
        """<style>
        div.stButton > button {width: 100%; border-radius: 8px;}
        </style>""",
        unsafe_allow_html=True
    )

    cols = st.columns(len(buttons) + 1)

    for i, (label, key) in enumerate(buttons):
        with cols[i]:
            type_btn = "primary" if st.session_state.get("page") == key else "secondary"
            if st.button(label, key=f"nav_{key}", type=type_btn):
                st.session_state.page = key
                st.rerun()

    with cols[-1]:
        with st.popover("👤 القائمة"):
            st.write(f"مرحباً {st.session_state.get('username','User')}")
            if st.button("➕ إضافة صفقة", key="menu_add_trade"):
                st.session_state.page = "add"
                st.rerun()
            if st.button("⚙️ إعدادات", key="menu_settings"):
                st.session_state.page = "settings"
                st.rerun()

            st.markdown("---")
            if st.button("🚪 خروج", key="menu_logout"):
                try:
                    from security import logout
                    logout()
                except Exception:
                    st.session_state.clear()
                    st.rerun()
