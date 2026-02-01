# ui/router.py
import streamlit as st
from analytics import calculate_portfolio_metrics, update_prices
from components import inject_component_styles, inject_streamlit_ar_i18n


def _ensure_ui_once():
    """Inject CSS + Arabic i18n once (safe)."""
    if st.session_state.get("_ui_injected_once"):
        return
    st.session_state["_ui_injected_once"] = True
    try:
        inject_component_styles()
    except Exception:
        pass
    try:
        inject_streamlit_ar_i18n(True)
    except Exception:
        pass


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
    current = st.session_state.get("page", "home")

    for i, (label, key) in enumerate(buttons):
        with cols[i]:
            type_btn = "primary" if current == key else "secondary"
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


def router():
    _ensure_ui_once()

    if "page" not in st.session_state:
        st.session_state.page = "home"

    render_navbar()
    pg = st.session_state.page

    fin = calculate_portfolio_metrics()

    # ✅ Import داخلي لتفادي Circular Import (views يستورد router)
    from views import (
        view_dashboard, view_portfolio, view_sukuk_portfolio, view_analysis,
        view_cash_log, view_backtester_ui, render_pulse_dashboard,
        view_add_trade, view_tools, view_settings
    )

    if pg == "home":
        view_dashboard(fin)
    elif pg == "spec":
        view_portfolio(fin, "spec")
    elif pg == "invest":
        view_portfolio(fin, "invest")
    elif pg == "sukuk":
        view_sukuk_portfolio(fin)
    elif pg == "analysis":
        view_analysis(fin)
    elif pg == "cash":
        view_cash_log(fin)
    elif pg == "backtest":
        view_backtester_ui(fin)
    elif pg == "pulse":
        render_pulse_dashboard()
    elif pg == "add":
        view_add_trade()
    elif pg == "tools":
        view_tools()
    elif pg == "settings":
        view_settings()
    elif pg == "update":
        with st.spinner("جاري التحديث..."):
            update_prices()
        st.cache_data.clear()
        st.rerun()
    else:
        st.session_state.page = "home"
        st.rerun()