import streamlit as st
from config import APP_NAME, APP_ICON, DEFAULT_COLORS
from datetime import date
import time
from logic import update_market_data_batch

def render_navbar():
    C = st.session_state.custom_colors
    st.markdown(f"""
    <div style="background-color: {C['card_bg']}; padding: 15px; border-bottom: 1px solid {C['border']}; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
        <div style="font-size: 1.5rem; font-weight: bold; color: {C['primary']};">{APP_ICON} {APP_NAME}</div>
        <div style="color: {C['sub_text']};">{date.today().strftime('%Y-%m-%d')}</div>
    </div>
    """, unsafe_allow_html=True)
    
    cols = st.columns(7)
    labels = ['الرئيسية', 'مضاربة', 'استثمار', 'السيولة', 'التحليل', 'إضافة صفقة', 'الإعدادات']
    keys = ['home', 'spec', 'invest', 'cash', 'analysis', 'add', 'settings']
    
    for col, label, key in zip(cols, labels, keys):
        if col.button(label, key=f"nav_{key}", use_container_width=True, type="primary" if st.session_state.page == key else "secondary"):
            st.session_state.page = key
            st.rerun()

    if st.button("تحديث الأسعار 🔄", use_container_width=True):
        with st.spinner("جاري التحديث..."):
            update_market_data_batch()
            st.rerun()

# ... (يمكنك نسخ بقية دوال العرض view_dashboard, view_portfolio من الكود السابق وضعها هنا)
