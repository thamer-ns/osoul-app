import importlib

import streamlit as st

from analytics import (
    calculate_portfolio_metrics,
    get_portfolio_cache_key,
    update_prices,
)
from tenant_scope import current_tenant
from views.shared import _ensure_ui_once

PAGES_REQUIRING_PORTFOLIO = {
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
def _get_portfolio_cache_key_fast(
    user_id: int,
    portfolio_id: int,
) -> str:
    """Return a tenant-specific revision key for global Streamlit cache."""
    revision = get_portfolio_cache_key()
    return f"u{int(user_id)}:p{int(portfolio_id)}:{revision}"


def _load_attr(module_name: str, attr_name: str):
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


def _render_page(page: str, finance):
    if page == "home":
        _load_attr("views.dashboard", "view_dashboard")(finance)
    elif page == "spec":
        _load_attr("views.portfolio", "view_portfolio")(finance, "spec")
    elif page == "invest":
        _load_attr("views.portfolio", "view_portfolio")(finance, "invest")
    elif page == "sukuk":
        _load_attr("views.sukuk", "view_sukuk_portfolio")(finance)
    elif page == "signals":
        _load_attr("views.signals", "view_signals")(finance)
    elif page == "analysis":
        _load_attr("views.analysis", "view_analysis")(finance)
    elif page == "cash":
        _load_attr("views.cash", "view_cash_log")(finance)
    elif page == "backtest":
        _load_attr("views.lab", "view_backtester_ui")(finance)
    elif page == "pulse":
        _load_attr("views.portfolio", "render_pulse_dashboard")()
    elif page == "add":
        _load_attr("views.portfolio", "view_add_trade")()
    elif page == "tools":
        _load_attr("views.settings", "view_tools")()
    elif page == "settings":
        _load_attr("views.settings", "view_settings")()
    else:
        st.session_state.page = "home"
        st.rerun()


def router():
    _ensure_ui_once()
    if "page" not in st.session_state:
        st.session_state.page = "home"

    _load_attr("views.navbar", "render_navbar")()
    page = st.session_state.page

    if page == "update":
        with st.spinner("جاري التحديث..."):
            update_prices()
        st.cache_data.clear()
        st.rerun()
        return

    finance = None
    if page in PAGES_REQUIRING_PORTFOLIO:
        tenant = current_tenant()
        if tenant is None:
            st.error("تعذر تحديد المحفظة النشطة بأمان.")
            st.stop()
        cache_key = _get_portfolio_cache_key_fast(
            tenant.user_id,
            tenant.portfolio_id,
        )
        with st.spinner("جارٍ تحميل بيانات المحفظة..."):
            finance = calculate_portfolio_metrics(cache_key=cache_key)

    _render_page(page, finance)
