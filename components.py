import streamlit as st
from datetime import date
from config import APP_NAME, APP_ICON

def render_navbar():
    C = st.session_state.custom_colors
    u = st.session_state.get('username', 'User')
    
    st.markdown(f"""
    <div style="background-color: {C.get('card_bg')}; padding: 20px; border-radius: 16px; border: 1px solid {C.get('border')}; margin-bottom: 25px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 4px 15px rgba(0,0,0,0.03);">
        <div style="display: flex; align-items: center; gap: 15px;">
            <div style="font-size: 2.5rem;">{APP_ICON}</div>
            <div>
                <h2 style="margin: 0; color: {C['primary']} !important; font-weight: 900;">{APP_NAME}</h2>
                <span style="font-size: 0.85rem; color: {C.get('sub_text')};">لوحة البيانات المالية الذكية</span>
            </div>
        </div>
        <div style="text-align: left; background-color: {C['page_bg']}; padding: 8px 15px; border-radius: 12px;">
            <div style="color: {C['primary']}; font-weight: 800;">مرحباً، {u}</div>
            <div style="font-weight: 700; color: {C.get('sub_text')}; direction: ltr;">{date.today().strftime('%Y-%m-%d')}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    cols = st.columns(9, gap="small")
    labels = ['الرئيسية', 'مضاربة', 'استثمار', 'السيولة', 'التحليل', 'إضافة', 'الإعدادات', 'تحديث', 'خروج']
    keys = ['home', 'spec', 'invest', 'cash', 'analysis', 'add', 'settings', 'update', 'logout']
    
    for col, label, key in zip(cols, labels, keys):
        active = (st.session_state.get('page') == key)
        if col.button(label, key=f"nav_{key}", type="primary" if active else "secondary", use_container_width=True):
            st.session_state.page = key
            st.rerun()
    st.markdown("---")

def render_kpi(label, value, color_condition=None):
    C = st.session_state.custom_colors
    val_c = C.get('main_text')
    
    if color_condition == "blue": val_c = C.get('primary')
    elif isinstance(color_condition, (int, float)):
        val_c = C.get('success') if color_condition >= 0 else C.get('danger')
            
    st.markdown(f"""<div class="kpi-box"><div style="color:{C['sub_text']}; font-size:0.9rem;">{label}</div><div class="kpi-value" style="color: {val_c} !important;">{value}</div></div>""", unsafe_allow_html=True)

def render_table(df, cols_def):
    if df.empty:
        st.info("لا توجد بيانات")
        return
    C = st.session_state.custom_colors
    headers = "".join([f"<th>{label}</th>" for _, label in cols_def])
    rows_html = ""
    for _, row in df.iterrows():
        cells = ""
        is_closed = str(row.get('status')).lower() in ['close', 'مغلقة']
        for k, _ in cols_def:
            val = row.get(k, "-")
            disp = val
            if k == 'status':
                bg, fg = ("#DCFCE7", "#166534") if not is_closed else ("#F3F4F6", "#4B5563")
                disp = f"<span style='background:{bg}; color:{fg}; padding:4px 12px; border-radius:20px; font-size:0.8rem; font-weight:800;'>{val}</span>"
            elif isinstance(val, (float, int)) and k not in ['quantity']:
                if k in ['gain', 'gain_pct', 'daily_change'] and not is_closed:
                    c = C['success'] if val >= 0 else C['danger']
                    disp = f"<span style='color:{c}; direction:ltr; font-weight:bold;'>{val:,.2f}</span>"
                else: disp = f"{val:,.2f}"
            elif 'date' in k and val: disp = str(val)[:10]
            cells += f"<td>{disp}</td>"
        rows_html += f"<tr>{cells}</tr>"
    st.markdown(f"""<div style="overflow-x: auto;"><table class="finance-table"><thead><tr>{headers}</tr></thead><tbody>{rows_html}</tbody></table></div>""", unsafe_allow_html=True)
