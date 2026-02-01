# views.py
"""
Compatibility layer (Phase 1):
- Keeps external imports stable: `from views import view_dashboard, ...`
- Router/Nav moved to: ui/router.py
- Implementation stays in: views_impl.py
"""

# ✅ Re-export pages from the implementation module
from views_impl import (
    view_dashboard,
    view_portfolio,
    view_sukuk_portfolio,
    view_analysis,
    view_cash_log,
    view_backtester_ui,
    render_pulse_dashboard,
    view_add_trade,
    view_tools,
    view_settings,

    # (اختياري) لو في ملفات ثانية تعتمد على هذي الواجهات المالية:
    render_financial_dashboard_ui,
    render_data_import_ui_content,
)

# ✅ Re-export router + navbar from ui/router.py
from ui.router import router as router
from ui.router import render_navbar as render_navbar

