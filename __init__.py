#views/__init__.py
import streamlit as st

from analytics import calculate_portfolio_metrics, update_prices

from views.shared import _ensure_ui_once
from views.navbar import render_navbar
from views.dashboard import view_dashboard
from views.portfolio import view_portfolio, render_pulse_dashboard, view_add_trade
from views.sukuk import view_sukuk_portfolio
from views.cash import view_cash_log
from views.lab import view_backtester_ui
from views.settings import view_settings, view_tools
from views.analysis import view_analysis

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
