"""Lazy page router for Osoli v2."""
from __future__ import annotations

import importlib

import streamlit as st

from analytics_v2 import calculate_portfolio_metrics, get_portfolio_cache_key, update_prices
from tenant_db import current_username
from views.shared import _ensure_ui_once

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
def _portfolio_revision(username: str) -> str:
    return get_portfolio_cache_key(username)


def _load(module_name: str, attribute: str):
    module = importlib.import_module(module_name)
    return getattr(module, attribute)


def _render_page(page: str, fin) -> None:
    if page == "home":
        _load("views.dashboard_v2", "view_dashboard")(fin)
    elif page == "spec":
        _load("views.portfolio_v2", "view_portfolio")(fin, "spec")
    elif page == "invest":
        _load("views.portfolio_v2", "view_portfolio")(fin, "invest")
    elif page == "sukuk":
        _load("views.portfolio_v2", "view_portfolio")(fin, "sukuk")
    elif page == "signals":
        _load("views.signals", "view_signals")(fin)
    elif page == "analysis":
        _load("views.analysis", "view_analysis")(fin)
    elif page == "cash":
        _load("views.cash_v2", "view_cash_log")(fin)
    elif page == "backtest":
        _load("views.lab", "view_backtester_ui")(fin)
    elif page == "pulse":
        _load("views.portfolio_v2", "render_pulse_dashboard")()
    elif page == "add":
        _load("views.portfolio_v2", "view_add_trade")()
    elif page == "tools":
        _load("views.settings", "view_tools")()
    elif page == "settings":
        _load("views.settings", "view_settings")()
    else:
        st.session_state.page = "home"
        st.rerun()


def router() -> None:
    _ensure_ui_once()
    username = current_username()

    if "page" not in st.session_state:
        st.session_state.page = "home"

    _load("views.navbar", "render_navbar")()
    page = st.session_state.page

    if page == "update":
        with st.spinner("جاري تحديث أسعار المستخدم الحالي..."):
            ok = update_prices(username)
        if ok:
            st.success("تم تحديث الأسعار.")
        else:
            st.warning("لم تكتمل بعض تحديثات الأسعار.")
        st.cache_data.clear()
        st.rerun()

    fin = None
    if page in _PAGES_REQUIRING_FIN:
        revision = _portfolio_revision(username)
        with st.spinner("جارٍ تحميل بيانات المحفظة..."):
            fin = calculate_portfolio_metrics(cache_key=revision, username=username)

    _render_page(page, fin)
