# ui/router.py
import streamlit as st
from analytics import calculate_portfolio_metrics, update_prices
from components import inject_component_styles, inject_streamlit_ar_i18n

# ✅ Pages
from ui.pages.dashboard import view_dashboard
from ui.pages.portfolio import view_portfolio
from ui.pages.sukuk import view_sukuk_portfolio

# ✅ Fail-safe import for advisor/analysis page (prevents app crash)
try:
    from ui.pages.analysis.page import view_analysis
    _analysis_import_error = None
except Exception as e:
    view_analysis = None
    _analysis_import_error = repr(e)

# ✅ باقي الصفحات حالياً من views_impl (مرحلة انتقالية)
from views_impl import (
    view_cash_log, view_backtester_ui, render_pulse_dashboard,
    view_add_trade, view_tools, view_settings
)


def _ensure_ui_once():
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


def safe_view_analysis(*args, **kwargs):
    """
    Use this instead of view_analysis to avoid crashing the whole app
    if analysis page imports fail.
    """
    if callable(view_analysis):
        try:
            return view_analysis(*args, **kwargs)
        except Exception as e:
            st.error("❌ تعذر تشغيل صفحة المستشار/التحليل.")
            st.info("📌 الخطأ حدث أثناء التنفيذ داخل view_analysis (وليس الاستيراد).")
            st.code(repr(e))
            return

    st.error("❌ تعذر تشغيل صفحة المستشار/التحليل (view_analysis).")
    st.info(
        "✅ الأسباب الأكثر شيوعًا:\n"
        "1) نقص ملف __init__.py داخل ui/ أو ui/pages/ أو ui/pages/analysis/\n"
        "2) خطأ Import داخل ui.pages.analysis.page (مكتبة ناقصة أو خطأ كود)\n"
        "3) ai_engine.py لا يحتوي generate / self_test\n"
    )
    if _analysis_import_error:
        st.code(_analysis_import_error)


def router():
    _ensure_ui_once()

    if "page" not in st.session_state:
        st.session_state.page = "home"

    render_navbar()
    pg = st.session_state.page

    fin = calculate_portfolio_metrics()

    if pg == "home":
        view_dashboard(fin)
    elif pg == "spec":
        view_portfolio(fin, "spec")
    elif pg == "invest":
        view_portfolio(fin, "invest")
    elif pg == "sukuk":
        view_sukuk_portfolio(fin)
    elif pg == "analysis":
        safe_view_analysis(fin)
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