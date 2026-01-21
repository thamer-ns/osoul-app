import streamlit as st
import pandas as pd

def render_navbar():
    c1, c2, c3, c4, c5, c6, c7, c8, c9 = st.columns([1, 1, 1, 1, 1, 1.2, 1, 1, 1])
    
    with c1:
        if st.button("🏠 الرئيسية", use_container_width=True): st.session_state.page = 'home'; st.rerun()
    with c2:
        if st.button("⚡ مضاربة", use_container_width=True): st.session_state.page = 'spec'; st.rerun()
    with c3:
        if st.button("💎 استثمار", use_container_width=True): st.session_state.page = 'invest'; st.rerun()
    with c4:
        if st.button("📜 صكوك", use_container_width=True): st.session_state.page = 'sukuk'; st.rerun()
    with c5:
        if st.button("🔍 تحليل", use_container_width=True): st.session_state.page = 'analysis'; st.rerun()
    with c6:
        if st.button("🧪 المختبر", use_container_width=True): st.session_state.page = 'backtest'; st.rerun()
    with c7:
        if st.button("📂 سجلات", use_container_width=True): st.session_state.page = 'cash'; st.rerun()
    with c8:
        if st.button("🔄 تحديث", use_container_width=True): st.session_state.page = 'update'; st.rerun()
        
    with c9:
        with st.popover("👤 القائمة"):
            st.write(f"مرحباً، {st.session_state.get('username', 'زائر')}")
            
            # === الزر الجديد ===
            if st.button("👤 الملف الشخصي", use_container_width=True): 
                st.session_state.page = 'profile'
                st.rerun()
            # ===================

            if st.button("➕ إضافة صفقة", use_container_width=True): st.session_state.page = 'add'; st.rerun()
            if st.button("🛠️ أدوات", use_container_width=True): st.session_state.page = 'tools'; st.rerun()
            if st.button("⚙️ الإعدادات", use_container_width=True): st.session_state.page = 'settings'; st.rerun()
            if st.button("🚪 خروج", use_container_width=True): 
                try:
                    from security import logout
                    logout()
                except ImportError:
                    st.session_state.clear()
                    st.rerun()
    
    st.markdown("---")

def render_kpi(label, value, color="blue"):
    text_color = "#172B4D"
    if color in ["success", "green"]: text_color = "#006644"
    elif color in ["danger", "red"]: text_color = "#DE350B"
    elif color == "blue": text_color = "#0052CC"

    st.markdown(f"""
    <div style="background: white; padding: 15px; border-radius: 8px; border: 1px solid #DFE1E6; text-align: center; margin-bottom: 10px;">
        <div style="color: #5E6C84; font-size: 0.85rem; font-weight: 600;">{label}</div>
        <div style="color: {text_color}; font-size: 1.5rem; font-weight: bold; direction: ltr;">{value}</div>
    </div>""", unsafe_allow_html=True)

def render_table(df, cols_definition):
    if df.empty:
        st.info("لا توجد بيانات.")
        return
    valid = [c for c, l in cols_definition if c in df.columns]
    rename = {c: l for c, l in cols_definition}
    st.dataframe(df[valid].rename(columns=rename), use_container_width=True, hide_index=True)
