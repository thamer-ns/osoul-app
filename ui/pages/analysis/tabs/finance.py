# ui/pages/analysis/tabs/finance.py
import streamlit as st


def render(symbol: str):
    try:
        import views_impl as v
        v.render_financial_dashboard_ui(symbol)
    except Exception as e:
        st.error(f"❌ تعذر فتح تبويب المالي: {e}")
