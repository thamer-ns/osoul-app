# ui/pages/analysis/tabs/classical.py
import streamlit as st


def render(symbol: str):
    try:
        import views_impl as v
        v.render_classical_analysis(symbol)
    except Exception as e:
        st.error(f"❌ تعذر فتح تبويب الكلاسيكي: {e}")
