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

    # تم إضافة "أدوات" للقائمة
    cols = st.columns(10, gap="small")
    labels = ['الرئيسية', 'مضاربة', 'استثمار', 'السيولة', 'التحليل', 'أدوات', 'إضافة', 'الإعدادات', 'تحديث', 'خروج']
    keys = ['home', 'spec', 'invest', 'cash', 'analysis', 'tools', 'add', 'settings', 'update', 'logout']
    
    for col, label, key in zip(cols, labels, keys):
        active = (st.session_state.get('page') == key)
        if col.button(label, key=f"nav_{key}", type="primary" if active else "secondary", use_container_width=True):
            st.session_state.page = key
            st.rerun()

def render_kpi(label, value, color_condition=None, help_text=None):
    C = st.session_state.custom_colors
    val_c = "#1F2937"
    
    if color_condition == "blue": val_c = "#0e6ba8"
    elif isinstance(color_condition, (int, float)):
        val_c = "#10B981" if color_condition >= 0 else "#EF4444"
    
    tooltip_attr = f'title="{help_text}"' if help_text else ''
    cursor_style = 'cursor: help;' if help_text else ''
            
    st.markdown(f"""
    <div class="kpi-box" {tooltip_attr} style="{cursor_style}">
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
            
            # منطق الألوان للأوزان (أخضر إذا تحقق الهدف، أحمر إذا انحرف)
            elif k == 'current_weight':
                try:
                    curr = float(val)
                    target = float(row.get('target_percentage', 0))
                    # هامش بسيط 1.5%
                    if target > 0:
                        if abs(curr - target) <= 1.5:
                            color = "#10B981" # أخضر (متحقق)
                        else:
                            color = "#EF4444" # أحمر (منحرف)
                    else:
                        color = "#0e6ba8"
                    disp = f"<span style='color:{color}; font-weight:bold;'>{curr:.2f}%</span>"
                except: disp = "-"
            
            elif k == 'target_percentage':
                try: disp = f"{float(val):.2f}%"
                except: disp = "-"

            elif k in ['gain', 'gain_pct', 'daily_change', 'remaining', 'net_profit', 'roi_pct', 'return_pct']:
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
            
            elif k in ['market_value', 'total_cost', 'entry_price', 'current_price', 'exit_price', 'total_dividends', 'suggested_amount', 'amount']:
                try: disp = "{:,.2f}".format(float(val))
                except: disp = val
                
            elif k in ['quantity', 'symbol_count', 'count']:
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
