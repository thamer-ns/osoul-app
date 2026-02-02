# ui/pages/analysis/tabs/ai.py
import streamlit as st

def render_tab(symbol: str, fin: dict, company_name: str = "", sector: str = ""):
    """
    Bridge to legacy UI (keeps the old screen exactly).
    """
    # Try legacy module first
    try:
        from ui.pages.analysis.ai_tab import render_tab as legacy_render  # type: ignore
        return legacy_render(symbol, fin, company_name=company_name, sector=sector)
    except Exception:
        pass

    # Fallback: if legacy used a different function name
    try:
        from ui.pages.analysis.ai_tab import view as legacy_view  # type: ignore
        return legacy_view(symbol, fin)
    except Exception:
        st.error("تعذر تحميل واجهة AI القديمة (ai_tab.py).")
        st.info("تأكد أن ai_tab.py يحتوي دالة render_tab أو view.")
