"""Lazy Streamlit page router with fast, unified hubs."""
from __future__ import annotations

import importlib
from typing import Any

import streamlit as st

PAGES_REQUIRING_PORTFOLIO = {
    "home",
    "portfolios",
    "insights",
    "cash",
}


def _portfolio_cache_key(user_id: int, portfolio_id: int) -> str:
    """Return a tenant-isolated key without database polling queries."""
    return f"u{int(user_id)}:p{int(portfolio_id)}"


def _load_attr(module_name: str, attr_name: str) -> Any:
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


def _render_page(page: str, finance: Any) -> None:
    routes = {
        "home": ("views.home", "view_home", (finance,)),
        "portfolios": ("views.portfolios", "view_portfolios", (finance,)),
        "insights": ("views.insights", "view_insights", (finance,)),
        "cash": ("views.cash", "view_cash_log", (finance,)),
        "tools": ("views.tools_core", "view_tools", ()),
        "settings": ("views.settings_core", "view_settings", ()),
    }
    target = routes.get(page)
    if target is None:
        _load_attr("views.navbar", "navigate_to")("home")
        return
    module_name, attr_name, args = target
    renderer = _load_attr(module_name, attr_name)
    if not callable(renderer):
        raise TypeError(f"Page renderer is not callable: {module_name}.{attr_name}")
    renderer(*args)


def router() -> None:
    if "page" not in st.session_state:
        st.session_state.page = "home"

    _load_attr("views.navbar", "render_navbar")()
    page = str(st.session_state.page or "home")

    if page == "update":
        from analytics import update_prices

        with st.spinner("جاري تحديث الأسعار..."):
            update_prices()
        _load_attr("views.navbar", "navigate_to")("home")
        return

    finance = None
    if page in PAGES_REQUIRING_PORTFOLIO:
        from analytics import calculate_portfolio_metrics
        from tenant_scope import current_tenant

        tenant = current_tenant()
        if tenant is None:
            st.error("تعذر تحديد المحفظة النشطة بأمان.")
            st.stop()
        cache_key = _portfolio_cache_key(
            tenant.user_id,
            tenant.portfolio_id,
        )
        with st.spinner("جارٍ تحميل بيانات المحفظة..."):
            finance = calculate_portfolio_metrics(cache_key=cache_key)
        if isinstance(finance, dict):
            finance["_cache_key"] = cache_key

    _render_page(page, finance)
