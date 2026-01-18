import streamlit as st
import pandas as pd
from config import APP_NAME, APP_ICON
from datetime import date
import time
from logic import update_market_data_batch

# دالة عرض القائمة العلوية (Navbar)
def render_navbar():
    # جلب الألوان واسم المستخدم
    C = st.session_state.custom_colors
    username = st.session_state.get('username', 'مستخدم')
    
    # --- 1. الهيدر العلوي (الشعار + اسم المستخدم) ---
    st.markdown(f"""
    <div style="background-color: {C['card_bg']}; padding: 15px 20px; border-radius: 10px; border: 1px solid {C['border']}; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.03);">
        <div style="font-size: 1.4rem; font-weight: 900; color: {C['primary']}; display: flex; align-items: center; gap: 10px;">
            <span style="font-size: 1.8rem;">{APP_ICON}</span> {APP_NAME}
        </div>
        <div style="text-align: left;">
            <div style="color: {C['primary']}; font-weight: bold; font-size: 0.95rem;">مرحباً، {username} 👋</div>
            <div style="color: {C['sub_text']}; font-size: 0.8rem; direction: ltr;">{date.today().strftime('%Y-%m-%d')}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # --- 2. أزرار التنقل (تمت إضافة زر الخروج هنا) ---
    # نستخدم 8 أعمدة بدلاً من 7 لإضافة زر الخروج
    cols = st.columns(8, gap="small")
    
    # قائمة العناوين والروابط
    labels = ['الرئيسية', 'مضاربة', 'استثمار', 'السيولة', 'التحليل', 'إضافة صفقة', 'الإعدادات', 'تسجيل خروج']
    keys = ['home', 'spec', 'invest', 'cash', 'analysis', 'add', 'settings', 'logout']
    
    for col, label, key in zip(cols, labels, keys):
        # تحديد الزر النشط لتلوينه
        is_active = (st.session_state.get('page') == key)
        
        # تنسيق خاص لزر الخروج
        if key == 'logout':
            if col.button(label, key=f"nav_{key}", use_container_width=True, type="secondary"):
                st.session_state.page = key
                st.rerun()
        else:
            # الأزرار العادية
            btn_type = "primary" if is_active else "secondary"
            if col.button(label, key=f"nav_{key}", use_container_width=True, type=btn_type):
                st.session_state.page = key
                # عند تغيير الصفحة، نلغي وضع التعديل إذا كان مفتوحاً
                if 'editing_id' in st.session_state: del st.session_state['editing_id']
                st.rerun()

    # --- 3. زر تحديث الأسعار ---
    st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)
    if st.button("تحديث الأسعار 🔄", use_container_width=True):
        with st.spinner("جاري الاتصال بالسوق وتحديث البيانات..."):
            update_market_data_batch()
            time.sleep(0.5)
            st.rerun()
    
    st.markdown("---")

# --- دوال العرض الأخرى (تأكد أن هذه الدوال موجودة في ملفك، أو انسخها من نسخنا السابقة) ---
# سأضع لك الدوال الأساسية هنا لضمان عمل الملف بالكامل

def render_kpi(label, value, color_condition=None):
    C = st.session_state.custom_colors
    val_c = C.get('main_text', '#000000')
    
    if color_condition is not None:
        if isinstance(color_condition, str) and color_condition == "blue":
             val_c = C.get('primary')
        elif isinstance(color_condition, (int, float)):
            if color_condition >= 0: val_c = C.get('success')
            else: val_c = C.get('danger')
            
    st.markdown(f"""<div class="kpi-box"><div class="kpi-title">{label}</div><div class="kpi-value" style="color: {val_c} !important;">{value}</div></div>""", unsafe_allow_html=True)

# (ملاحظة: تأكد من أن باقي الدوال مثل view_dashboard, view_portfolio موجودة في هذا الملف كما كانت سابقاً)
# إذا كانت مفقودة، أخبرني لأرسل لك الملف كاملاً مع جميع الدوال.
