import streamlit as st
from datetime import date
from config import APP_NAME, APP_ICON

def render_navbar():
    if 'custom_colors' not in st.session_state:
        from config import DEFAULT_COLORS
        st.session_state.custom_colors = DEFAULT_COLORS.copy()
    C = st.session_state.custom_colors
    u = st.session_state.get('username', 'المستثمر')
    
    st.markdown(f"""
    <div style="background: white; padding: 15px; border-radius: 12px; border: 1px solid #E5E7EB; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
        <div style="display: flex; align-items: center; gap: 10px;">
            <div style="font-size: 1.8rem;">{APP_ICON}</div>
            <div style="font-weight: 900; font-size: 1.4rem; color: #0e6ba8;">{APP_NAME}</div>
        </div>
        <div style="font-weight: 700; color: #6B7280; font-size: 0.9rem;">
            {date.today().strftime('%Y-%m-%d')} | {u}
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

def render_kpi(label, value, color_condition=None):
    C = st.session_state.custom_colors
    val_c = "#1F2937"
    
    if color_condition == "blue": val_c = "#0e6ba8"
    elif isinstance(color_condition, (int, float)):
        val_c = "#10B981" if color_condition >= 0 else "#EF4444"
            
    st.markdown(f"""
    <div class="kpi-box">
        <div style="color:#6B7280; font-size:0.8rem; font-weight:700; margin-bottom:5px;">{label}</div>
        <div class="kpi-value" style="color: {val_c} !important; direction:ltr;">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def render_table(df, cols_def):
    if df.empty:
        st.info("لا توجد بيانات متاحة")
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
            
            if 'date' in k and val:
                disp = str(val)[:10]

            elif k == 'status':
                if is_closed:
                    bg, fg, txt = ("#F3F4F6", "#4B5563", "مغلقة")
                else:
                    bg, fg, txt = ("#DCFCE7", "#166534", "مفتوحة") 
                disp = f"<span style='background:{bg}; color:{fg}; padding:5px 15px; border-radius:20px; font-size:0.8rem; font-weight:800;'>{txt}</span>"
            
            # تم إضافة 'remaining' هنا لتلوين عمود "المتبقي للهدف"
            elif k in ['gain', 'gain_pct', 'daily_change', 'remaining']:
                if is_closed and k == 'daily_change':
                    disp = "<span style='color:#9CA3AF'>-</span>"
                else:
                    try:
                        num_val = float(val)
                        c = "#10B981" if num_val >= 0 else "#EF4444"
                        suffix = "%" if 'pct' in k or 'change' in k or 'weight' in k else ""
                        fmt = "{:,.2f}".format(num_val)
                        disp = f"<span style='color:{c}; direction:ltr; font-weight:bold;'>{fmt}{suffix}</span>"
                    except: disp = val
            
            elif k in ['local_weight', 'target_weight', 'current_weight']:
                 try:
                    num = float(val)
                    disp = f"<span style='color:#0e6ba8; font-weight:bold;'>{num:.2f}%</span>"
                 except: disp = "-"

            elif k in ['market_value', 'total_cost', 'entry_price', 'current_price', 'exit_price']:
                try: disp = "{:,.2f}".format(float(val))
                except: disp = val
                
            elif k in ['quantity', 'symbol_count', 'count']: # symbol_count للجدول الجديد
                try: disp = "{:,.0f}".format(float(val))
                except: disp = val

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
