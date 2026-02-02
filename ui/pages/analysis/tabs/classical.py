# ui/pages/analysis/tabs/classical.py
import streamlit as st

try:
    from classical_analysis import render_classical_analysis
except Exception:
    render_classical_analysis = None


def render_tab(symbol: str, fin: dict, company_name: str = "", sector: str = ""):
    if not render_classical_analysis:
        st.warning("⚠️ ملف classical_analysis.py غير متوفر أو به خطأ.")
        return
    render_classical_analysis(symbol)
