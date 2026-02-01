# views.py
# ✅ Facade layer: keep imports stable while real code lives in views_impl + ui.pages

from ui.pages.dashboard import view_dashboard
from ui.pages.portfolio import view_portfolio
from ui.pages.sukuk import view_sukuk_portfolio
from ui.pages.cash import view_cash_log

# ✅ Analysis moved to ui.pages.analysis.main (tabs split)
from ui.pages.analysis.main import view_analysis

from views_impl import (
    view_backtester_ui, render_pulse_dashboard,
    view_add_trade, view_tools, view_settings
)

# ✅ Router lives in ui/router.py now
from ui.router import router as router
from ui.router import render_navbar as render_navbar
