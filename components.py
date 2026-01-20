import streamlit as st
from config import APP_NAME, APP_ICON

def render_navbar():
    if 'custom_colors' not in st.session_state:
        from config import DEFAULT_COLORS
        st.session_state.custom_colors = DEFAULT_COLORS.copy()
    
    with st.container():
        c_logo, c_nav, c_user = st.columns([1.5, 6, 1.5], gap="small")
        with c_logo:
            st.markdown(f"""<div style="display:flex;align-items:center;gap:10px;padding-top:5px;"><div class="app-logo-box">{APP_ICON}</div><div><div class="logo-text">{APP_NAME}</div></div></div>""", unsafe_allow_html=True)
            
        with c_nav:
            cols = st.columns(7, gap="small")
            nav_items = [("الرئيسة", "home"), ("مضاربة", "spec"), ("استثمار", "invest"), ("صكوك", "sukuk"), ("تحليل", "analysis"), ("سيولة", "cash"), ("تحديث", "update")]
            for col, (label, key) in zip(cols, nav_items):
                is_active = (st.session_state.get('page') == key)
                with col:
                    btn_type = "primary" if is_active else "secondary"
                    if st.button(label, key=f"nav_{key}", type=btn_type, use_container_width=True):
                        st.session_state.page = key; st.rerun()
        
        with c_user:
            with st.popover("👤 المستثمر", use_container_width=True):
                if st.button("➕ إضافة", key="u_add", use_container_width=True): st.session_state.page = "add"; st.rerun()
                if st.button("⚙️ إعدادات", key="u_set", use_container_width=True): st.session_state.page = "settings"; st.rerun()
                if st.button("🛠️ أدوات", key="u_tools", use_container_width=True): st.session_state.page = "tools"; st.rerun()
    st.markdown("---")

def render_kpi(label, value, color_condition=None, help_text=None):
    C = st.session_state.custom_colors
    val_c = C['main_text']
    if color_condition == "blue": val_c = C['primary']
    elif color_condition == "success": val_c = C['success']
    elif isinstance(color_condition, (int, float)): val_c = C['success'] if color_condition >= 0 else C['danger']
    
    tooltip = f'title="{help_text}"' if help_text else ''
    st.markdown(f"""<div class="kpi-box" {tooltip}><div style="color:{C['sub_text']};font-size:0.85rem;font-weight:700;margin-bottom:8px;">{label}</div><div class="kpi-value" style="color:{val_c} !important;">{value}</div></div>""", unsafe_allow_html=True)

def render_table(df, cols_def):
    """
    هذه الدالة هي المسؤولة عن توحيد شكل الجداول في البرنامج كاملاً.
    تقوم برسم جدول HTML يستخدم كلاس .finance-table المعرف في config.py
    """
    if df.empty: st.info("لا توجد بيانات لعرضها"); return
    
    headers = "".join([f"<th>{label}</th>" for _, label in cols_def])
    rows_html = ""
    
    for _, row in df.iterrows():
        cells = ""
        # التحقق من حالة الإغلاق للتلوين الباهت إذا لزم الأمر
        is_closed = str(row.get('status', '')).lower() in ['close', 'sold', 'مغلقة']
        row_style = "opacity: 0.6;" if is_closed else ""
        
        for k, _ in cols_def:
            val = row.get(k, "-")
            disp = val
            
            # تنسيق التاريخ
            if 'date' in k and val: disp = str(val)[:10]
            
            # تنسيق الأرقام والنسب
            elif isinstance(val, (int, float)):
                fmt_num = "{:,.2f}".format(float(val))
                
                # تلوين الأرقام (أخضر/أحمر)
                if k in ['gain', 'gain_pct', 'net_profit', 'daily_change', 'roi_pct']:
                    color = "#10B981" if val >= 0 else "#EF4444"
                    suffix = "%" if 'pct' in k or 'change' in k else ""
                    disp = f"<span style='color:{color};font-weight:bold;direction:ltr;'>{fmt_num}{suffix}</span>"
                
                # تلوين الأوزان
                elif k == 'current_weight' or k == 'target_percentage':
                     disp = f"{fmt_num}%"
                
                # عرض الملايين (للقوائم المالية)
                elif isinstance(val, float) and val > 1_000_000 and k in ['revenue', 'net_income']:
                    disp = f"{val/1_000_000:.1f}M"
                    
                else:
                    disp = fmt_num
                    
            cells += f"<td>{disp}</td>"
        rows_html += f"<tr style='{row_style}'>{cells}</tr>"
        
    st.markdown(f"""
    <div style="overflow-x: auto; margin-bottom: 20px;">
        <table class="finance-table">
            <thead><tr>{headers}</tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>""", unsafe_allow_html=True)
