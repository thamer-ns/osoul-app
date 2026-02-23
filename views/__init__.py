import importlib
import streamlit as st

from analytics import calculate_portfolio_metrics, update_prices, get_portfolio_cache_key
from views.shared import _ensure_ui_once

# صفحات تحتاج تحميل بيانات المحفظة/التدفقات قبل العرض
_PAGES_REQUIRING_FIN = {
    "home",
    "spec",
    "invest",
    "sukuk",
    "signals",
    "analysis",
    "cash",
    "backtest",
}


@st.cache_data(ttl=5, show_spinner=False)
def _get_portfolio_cache_key_fast() -> str:
    """تقليل ضغط قاعدة البيانات عند التنقل السريع بين الصفحات.

    يبقى التحديث شبه فوري (5 ثوانٍ) ويُكسر أيضًا عند استدعاء st.cache_data.clear().
    """
    return get_portfolio_cache_key()


def _load_attr(module_name: str, attr_name: str):
    mod = importlib.import_module(module_name)
    return getattr(mod, attr_name)


def _render_page(pg: str, fin):
    """استيراد كسول للصفحات الثقيلة لتسريع التبديل وتقليل تحميل البداية."""
    if pg == "home":
        _load_attr("views.dashboard", "view_dashboard")(fin)
    elif pg == "spec":
        _load_attr("views.portfolio", "view_portfolio")(fin, "spec")
    elif pg == "invest":
        _load_attr("views.portfolio", "view_portfolio")(fin, "invest")
    elif pg == "sukuk":
        _load_attr("views.sukuk", "view_sukuk_portfolio")(fin)
    elif pg == "signals":
        _load_attr("views.signals", "view_signals")(fin)
    elif pg == "analysis":
        _load_attr("views.analysis", "view_analysis")(fin)
    elif pg == "cash":
        _load_attr("views.cash", "view_cash_log")(fin)
    elif pg == "backtest":
        _load_attr("views.lab", "view_backtester_ui")(fin)
    elif pg == "pulse":
        _load_attr("views.portfolio", "render_pulse_dashboard")()
    elif pg == "add":
        _load_attr("views.portfolio", "view_add_trade")()
    elif pg == "tools":
        _load_attr("views.settings", "view_tools")()
    elif pg == "settings":
        _load_attr("views.settings", "view_settings")()
    else:
        st.session_state.page = "home"
        st.rerun()


def router():
    _ensure_ui_once()

    if "page" not in st.session_state:
        st.session_state.page = "home"

    # استيراد navbar بشكل كسول أيضًا (يحمل أسرع في بعض البيئات)
    _load_attr("views.navbar", "render_navbar")()
    pg = st.session_state.page

    if pg == "update":
        with st.spinner("جاري التحديث..."):
            update_prices()
        st.cache_data.clear()
        st.rerun()
        return

    fin = None
    if pg in _PAGES_REQUIRING_FIN:
        with st.spinner("جارٍ تحميل بيانات المحفظة..."):
            fin = calculate_portfolio_metrics(cache_key=_get_portfolio_cache_key_fast())

    _render_page(pg, fin)
