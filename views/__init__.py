"""Lazy Streamlit page router."""
from __future__ import annotations

import importlib

import streamlit as st

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


@st.cache_data(ttl=45, max_entries=256, show_spinner=False)
def _get_portfolio_cache_key_fast(user_id: int, portfolio_id: int) -> str:
    """Return a tenant-specific data revision without polling on every widget click."""
    from analytics import get_portfolio_cache_key

    revision = get_portfolio_cache_key()
    return f"u{int(user_id)}:p{int(portfolio_id)}:{revision}"


def _load_attr(module_name: str, attr_name: str):
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


def _render_page(page: str, finance):
    routes = {
        "home": ("views.dashboard", "view_dashboard", (finance,)),
        "spec": ("views.portfolio", "view_portfolio", (finance, "spec")),
        "invest": ("views.portfolio", "view_portfolio", (finance, "invest")),
        "sukuk": ("views.sukuk", "view_sukuk_portfolio", (finance,)),
        "signals": ("views.signals", "view_signals", (finance,)),
        "analysis": ("views.analysis", "view_analysis", (finance,)),
        "cash": ("views.cash", "view_cash_log", (finance,)),
        "backtest": ("views.lab", "view_backtester_ui", (finance,)),
        "pulse": ("views.portfolio", "render_pulse_dashboard", ()),
        "add": ("views.portfolio", "view_add_trade", ()),
        "tools": ("views.settings", "view_tools", ()),
        "settings": ("views.settings", "view_settings", ()),
    }
    target = routes.get(page)
    if target is None:
        st.session_state.page = "home"
        st.rerun()
        return
    module_name, attr_name, args = target
    _load_attr(module_name, attr_name)(*args)


def router():
    if "page" not in st.session_state:
        st.session_state.page = "home"

    _load_attr("views.navbar", "render_navbar")()
    page = str(st.session_state.page or "home")

    if page == "update":
        from analytics import update_prices

        with st.spinner("جاري تحديث الأسعار..."):
            update_prices()
        st.cache_data.clear()
        st.session_state.page = "home"
        st.rerun()
        return

    finance = None
    if page in PAGES_REQUIRING_PORTFOLIO:
        from analytics import calculate_portfolio_metrics
        from tenant_scope import current_tenant

        tenant = current_tenant()
        if tenant is None:
            st.error("تعذر تحديد المحفظة النشطة بأمان.")
            st.stop()
        cache_key = _get_portfolio_cache_key_fast(tenant.user_id, tenant.portfolio_id)
        with st.spinner("جارٍ تحميل بيانات المحفظة..."):
            finance = calculate_portfolio_metrics(cache_key=cache_key)
        if isinstance(finance, dict):
            finance["_cache_key"] = cache_key

    _render_page(page, finance)
