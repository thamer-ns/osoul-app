# ui/pages/analysis/classical_tab.py
import streamlit as st

try:
    from classical_analysis import render_classical_analysis
except Exception:
    def render_classical_analysis(s):
        st.warning("⚠️ ملف classical_analysis.py مفقود أو به خطأ.")


def render_classical_tab(symbol: str):
    render_classical_analysis(symbol)
