import streamlit as st
import pandas as pd

def render_navbar():
    """عرض شريط التنقل العلوي مع زر المختبر الجديد"""
    # ترتيب الأزرار: الرئيسية | مضاربة | استثمار | صكوك | تحليل | المختبر | سجلات | تحديث | القائمة
    
    # تقسيم الأعمدة لتسع الأزرار الجديدة
    c1, c2, c3, c4, c5, c6, c7, c8, c9 = st.columns([1, 1, 1, 1, 1, 1.2, 1, 1, 1])
    
    with c1:
        if st.button("🏠 الرئيسية", use_container_width=True): 
            st.session_state.page = 'home'
            st.rerun()
    with c2:
        if st.button("⚡ مضاربة", use_container_width=True): 
            st.session_state.page = 'spec'
            st.rerun()
    with c3:
        if st.button("💎 استثمار", use_container_width=True): 
            st.session_state.page = 'invest'
            st.rerun()
    with c4:
        if st.button("📜 صكوك", use_container_width=True): 
            st.session_state.page = 'sukuk'
            st.rerun()
    with c5:
        if st.button("🔍 تحليل", use_container_width=True): 
            st.session_state.page = 'analysis'
            st.rerun()
    
    # --- هذا هو الزر الجديد (المختبر) ---
    with c6:
        if st.button("🧪 المختبر", use_container_width=True): 
            st.session_state.page = 'backtest'
            st.rerun()
    # -----------------------------------

    with c7:
        if st.button("📂 سجلات", use_container_width=True): 
            st.session_state.page = 'cash'
            st.rerun()
    with c8:
        if st.button("🔄 تحديث", use_container_width=True): 
            st.session_state.page = 'update'
            st.rerun()
        
    with c9:
        with st.popover("👤 القائمة"):
            st.write(f"مرحباً، {st.session_state.get('username', 'زائر')}")
            if st.button("➕ إضافة صفقة", use_container_width=True): 
                st.session_state.page = 'add'
                st.rerun()
            if st.button("🛠️ أدوات", use_container_width=True): 
                st.session_state.page = 'tools'
                st.rerun()
            if st.button("⚙️ الإعدادات", use_container_width=True): 
                st.session_state.page = 'settings'
                st.rerun()
            if st.button("🚪 خروج", use_container_width=True): 
                try:
                    from security import logout
                    logout()
                except ImportError:
                    st.session_state.clear()
                    st.rerun()
    
    st.markdown("---")

def render_kpi(label, value, color="blue"):
    """دالة مساعدة لعرض البطاقات الإحصائية (KPI Cards)"""
    # تحديد اللون بناءً على المدخلات
    text_color = "#172B4D" # اللون الافتراضي للنص
    if color == "success" or color == "green":
        text_color = "#006644"
    elif color == "danger" or color == "red":
        text_color = "#DE350B"
    elif color == "blue":
        text_color = "#0052CC"

    st.markdown(f"""
    <div style="
        background-color: white;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #DFE1E6;
        text-align: center;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        margin-bottom: 10px;
    ">
        <div style="color: #5E6C84; font-size: 0.85rem; font-weight: 600; margin-bottom: 5px;">{label}</div>
        <div style="color: {text_color}; font-size: 1.5rem; font-weight: bold; direction: ltr;">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def render_table(df, cols_definition):
    """دالة مساعدة لعرض الجداول بتنسيق موحد مع إعادة تسمية الأعمدة"""
    if df.empty:
        st.info("لا توجد بيانات لعرضها.")
        return

    # استخراج أسماء الأعمدة الموجودة فقط في الداتا فريم لتجنب الأخطاء
    valid_cols = [col for col, label in cols_definition if col in df.columns]
    
    # خريطة إعادة التسمية (من الانجليزي للعربي)
    rename_map = {col: label for col, label in cols_definition}
    
    # تجهيز الجدول للعرض
    display_df = df[valid_cols].rename(columns=rename_map)
    
    # عرض الجدول
    st.dataframe(
        display_df, 
        use_container_width=True, 
        hide_index=True
    )
