import streamlit as st
from datetime import date
from config import APP_NAME, APP_ICON

def render_navbar():
    C = st.session_state.custom_colors
    u = st.session_state.get('username', 'User')
    
    st.markdown(f"""
    <div style="background-color: {C.get('card_bg')}; padding: 15px 20px; border-radius: 16px; border: 1px solid {C.get('border')}; margin-bottom: 25px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 4px 15px rgba(0,0,0,0.03);">
        <div style="display: flex; align-items: center; gap: 15px;">
            <div style="font-size: 2.2rem;">{APP_ICON}</div>
            <div>
                <h2 style="margin: 0; color: {C['primary']} !important; font-weight: 900; font-size: 1.5rem;">{APP_NAME}</h2>
                <span style="font-size: 0.8rem; color: {C.get('sub_text')}; font-weight: 600;">لوحة البيانات المالية</span>
            </div>
        </div>
        <div style="text-align: left; background-color: {C['page_bg']}; padding: 8px 15px; border-radius: 12px;">
            <div style="color: {C['primary']}; font-weight: 800; font-size: 0.9rem;">{u}</div>
            <div style="font-weight: 700; color: {C.get('sub_text')}; font-size: 0.8rem; direction: ltr;">{date.today().strftime('%Y-%m-%d')}</div>
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
            
    st.markdown(f"""
    <div class="kpi-box">
        <div style="color:{C['sub_text']}; font-size:0.85rem; font-weight:600; margin-bottom:5px;">{label}</div>
        <div class="kpi-value" style="color: {val_c} !important;">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def render_table(df, cols_def):
    if df.empty:
        st.info("لا توجد بيانات متاحة للعرض")
        return

    C = st.session_state.custom_colors
    headers = "".join([f"<th>{label}</th>" for _, label in cols_def])
    rows_html = ""
    
    for _, row in df.iterrows():
        cells = ""
        status_val = str(row.get('status', '')).lower()
        is_closed = status_val in ['close', 'sold', 'مغلقة', 'مباعة']
        
        for k, _ in cols_def:
            val = row.get(k, "-")
            disp = val
            
            # معالجة تاريخ البيع: يظهر فقط للمغلقة
            if k == 'exit_date':
                if not is_closed: disp = "-"
                elif val: disp = str(val)[:10]

            elif k == 'status':
                if is_closed:
                    bg, fg, txt = ("#F3F4F6", "#4B5563", "مغلقة")
                else:
                    bg, fg, txt = ("#DCFCE7", "#166534", "مفتوحة")
                disp = f"<span style='background:{bg}; color:{fg}; padding:4px 10px; border-radius:12px; font-size:0.75rem; font-weight:800;'>{txt}</span>"
            
            elif k in ['gain', 'gain_pct', 'daily_change']:
                if is_closed and k == 'daily_change':
                    disp = "<span style='color:#9CA3AF'>-</span>"
                else:
                    try:
                        num_val = float(val)
                        c = C['success'] if num_val >= 0 else C['danger']
                        suffix = "%" if 'pct' in k or 'change' in k else ""
                        fmt = "{:,.2f}".format(num_val)
                        disp = f"<span style='color:{c}; direction:ltr; font-weight:bold;'>{fmt}{suffix}</span>"
                    except: disp = val

            elif k in ['market_value', 'total_cost', 'entry_price', 'current_price', 'year_high', 'year_low']:
                try: disp = "{:,.2f}".format(float(val))
                except: disp = val
            
            # الوزن النسبي
            elif k == 'local_weight':
                try:
                    num = float(val)
                    if num == 0: disp = "-"
                    else: disp = f"{num:.2f}%"
                except: disp = "-"
                
            elif k in ['quantity']:
                try: disp = "{:,.0f}".format(float(val))
                except: disp = val
                
            elif 'date' in k and val:
                disp = str(val)[:10]

            cells += f"<td>{disp}</td>"
        rows_html += f"<tr>{cells}</tr>"
        
    st.markdown(f"""
    <div style="overflow-x: auto;">
        <table class="finance-table">
            <thead><tr>{headers}</tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)
