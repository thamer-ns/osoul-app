# views.py
# ✅ Facade layer: keep imports stable while real code lives in views_impl + ui.pages

import streamlit as st

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

from views_impl import (
    view_cash_log,
    view_backtester_ui,
    render_pulse_dashboard,
    view_add_trade,
    view_tools,
    view_settings,
)

# ✅ Router lives in ui/router.py now
from ui.router import router as router
from ui.router import render_navbar as render_navbar


def safe_view_analysis(*args, **kwargs):
    """
    Use this instead of view_analysis to avoid crashing the whole app
    if analysis page imports fail.
    """
    if callable(view_analysis):
        return view_analysis(*args, **kwargs)

    st.error("❌ تعذر تشغيل صفحة المستشار/التحليل (view_analysis).")
    st.info(
        "✅ الأسباب الأكثر شيوعًا:\n"
        "1) نقص ملف __init__.py داخل ui/ أو ui/pages/ أو ui/pages/analysis/\n"
        "2) خطأ Import داخل ui.pages.analysis.page (مكتبة ناقصة أو خطأ كود)\n"
    )
    if _analysis_import_error:
        st.code(_analysis_import_error)