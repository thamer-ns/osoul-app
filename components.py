import streamlit as st
from config import APP_NAME, APP_ICON

def render_navbar():
    # (نفس الكود السابق للناف بار)
    if 'custom_colors' not in st.session_state:
        from config import DEFAULT_COLORS
        st.session_state.custom_colors = DEFAULT_COLORS.copy()
    
    with st.container():
        c1, c2, c3 = st.columns([1.5, 6, 1.5])
        with c1:
            st.markdown(f"<h3 style='margin:0; color:#0052CC;'>{APP_ICON} {APP_NAME}</h3>", unsafe_allow_html=True)
        with c2:
            cols = st.columns(7)
            menu = [("الرئيسة", "home"), ("مضاربة", "spec"), ("استثمار", "invest"), ("صكوك", "sukuk"), ("تحليل", "analysis"), ("سجلات", "cash"), ("تحديث", "update")]
            for col, (title, page) in zip(cols, menu):
                with col:
                    active = st.session_state.get('page') == page
                    if st.button(title, key=f"nav_{page}", type="primary" if active else "secondary", use_container_width=True):
                        st.session_state.page = page; st.rerun()
        with c3:
            with st.popover("👤 القائمة"):
                if st.button("➕ صفقة جديدة", use_container_width=True): st.session_state.page = 'add'; st.rerun()
                if st.button("⚙️ الإعدادات", use_container_width=True): st.session_state.page = 'settings'; st.rerun()

    st.markdown("---")

def render_kpi(label, value, color=None):
    c = "black"
    if color == 'green': c = "#006644"
    elif color == 'red': c = "#DE350B"
    elif color == 'blue': c = "#0052CC"
    
    st.markdown(f"""
    <div class="kpi-box">
        <div class="kpi-label">{label}</div>
        <div class="kpi-val" style="color:{c} !important;">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def render_table(df, cols_definition):
    """
    يقوم برسم جدول مطابق تماماً للتصميم الأصلي (سكرين شوت 428)
    """
    if df.empty:
        st.info("لا توجد بيانات للعرض")
        return

    headers = ""
    for _, title in cols_definition:
        headers += f"<th>{title}</th>"

    rows = ""
    for _, row in df.iterrows():
        cells = ""
        is_closed = str(row.get('status', '')).lower() in ['close', 'sold', 'مغلقة']
        style = "opacity: 0.6; background: #F4F5F7;" if is_closed else ""
        
        for col_key, _ in cols_definition:
            val = row.get(col_key, "-")
            display_val = val
            
            # 1. تنسيق الحالة (مفتوحة/مغلقة)
            if col_key == 'status':
                if not is_closed:
                    display_val = f"<span style='background:#E3FCEF; color:#006644; padding:2px 8px; border-radius:4px; font-size:0.8rem;'>مفتوحة</span>"
                else:
                    display_val = f"<span style='background:#DFE1E6; color:#42526E; padding:2px 8px; border-radius:4px; font-size:0.8rem;'>مغلقة</span>"
            
            # 2. تنسيق الأرقام والنسب
            elif isinstance(val, (int, float)):
                fmt = "{:,.2f}".format(val)
                
                # تلوين الربح والخسارة
                if col_key in ['gain', 'gain_pct', 'daily_change', 'net_profit', 'change']:
                    color = "#006644" if val >= 0 else "#DE350B"
                    suffix = "%" if 'pct' in col_key or 'change' in col_key else ""
                    # جعل الخط عريض للقيم المهمة
                    weight = "bold" if col_key in ['gain', 'gain_pct'] else "normal"
                    display_val = f"<span style='color:{color}; font-weight:{weight}; direction:ltr;'>{fmt}{suffix}</span>"
                
                # تنسيق النسب العادية
                elif 'weight' in col_key or 'percentage' in col_key:
                    display_val = f"{fmt}%"
                    
                # الملايين (للقوائم المالية)
                elif val > 1_000_000 and col_key in ['revenue', 'net_income']:
                     display_val = f"{val/1_000_000:,.1f}M"
                else:
                    display_val = fmt

            # 3. تنسيق التواريخ
            elif 'date' in col_key and val:
                display_val = str(val)[:10]

            cells += f"<td>{display_val}</td>"
        rows += f"<tr style='{style}'>{cells}</tr>"

    st.markdown(f"""
    <div class="finance-table-container">
        <table class="finance-table">
            <thead><tr>{headers}</tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)
