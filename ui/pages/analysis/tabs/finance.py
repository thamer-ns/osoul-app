import streamlit as st


def render_tab(fin: dict, symbol: str):
    """
    تبويب التحليل المالي
    يعتمد على render_financial_dashboard_ui الموجودة داخل views_impl.py لضمان التطابق.
    """
    try:
        from views_impl import render_financial_dashboard_ui
    except Exception as e:
        st.error("❌ تعذر تحميل تبويب المالي بسبب مشكلة في views_impl.py")
        st.code(str(e))
        return

    render_financial_dashboard_ui(symbol)
