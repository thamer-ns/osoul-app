import streamlit as st
from config import APP_NAME, APP_ICON

def render_navbar():
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
                    btn_type = "primary" if active else "secondary"
                    if st.button(title, key=f"nav_{page}", type=btn_type, use_container_width=True):
                        if page == "update": st.session_state.page = "update"
                        else: st.session_state.page = page
                        st.rerun()
        with c3:
            with st.popover("👤 القائمة"):
                if st.button("➕ صفقة جديدة", use_container_width=True): st.session_state.page = 'add'; st.rerun()
                if st.button("⚙️ الإعدادات", use_container_width=True): st.session_state.page = 'settings'; st.rerun()

    st.markdown("---")

def render_kpi(label, value, color=None):
    c = "black"
    if color == 'green' or color == 'success': c = "#006644"
    elif color == 'red' or color == 'danger': c = "#DE350B"
    elif color == 'blue' or color == 'primary': c = "#0052CC"
    
    st.markdown(f"""
    <div class="kpi-box">
        <div class="kpi-label">{label}</div>
        <div class="kpi-val" style="color:{c} !important;">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def render_table(df, cols_def):
    if df.empty:
        st.info("لا توجد بيانات للعرض")
        return

    headers = ""
    # التعامل المرن سواء كانت cols_def قائمة بسيطة أو قائمة أزواج
    if cols_def and isinstance(cols_def[0], tuple):
        for _, title in cols_def:
            headers += f"<th>{title}</th>"
        col_keys = [k for k, _ in cols_def]
    else:
        # حالة احتياطية لو تم تمرير قائمة بسيطة
        for title in cols_def:
            headers += f"<th>{title}</th>"
        col_keys = df.columns

    rows_html = ""
    for _, row in df.iterrows():
        cells = ""
        is_closed = str(row.get('status', '')).lower() in ['close', 'sold', 'مغلقة', 'مباعة']
        
        for k in col_keys:
            val = row.get(k, "-")
            disp = val
            key_str = str(k).lower()
            
            if 'date' in key_str and val:
                disp = str(val)[:10]
            elif key_str == 'status':
                if not is_closed:
                    disp = f"<span style='background:#E3FCEF; color:#006644; padding:2px 8px; border-radius:4px; font-size:0.8rem;'>مفتوحة</span>"
                else:
                    disp = f"<span style='background:#DFE1E6; color:#42526E; padding:2px 8px; border-radius:4px; font-size:0.8rem;'>مغلقة</span>"
            elif isinstance(val, (int, float)) or (isinstance(val, str) and val.replace('.','',1).isdigit()):
                try:
                    num = float(val)
                    fmt_num = "{:,.2f}".format(num)
                    if key_str in ['gain', 'gain_pct', 'net_profit', 'roi_pct', 'daily_change', 'change']:
                        color = "#006644" if num >= 0 else "#DE350B"
                        suffix = "%" if 'pct' in key_str or 'change' in key_str else ""
                        weight = "bold" if key_str in ['gain', 'gain_pct'] else "600"
                        if is_closed and key_str == 'daily_change': disp = "<span style='color:#9CA3AF'>-</span>"
                        else: disp = f"<span style='color:{color}; font-weight:{weight}; direction:ltr;'>{fmt_num}{suffix}</span>"
                    elif key_str == 'current_weight':
                        disp = f"<span style='font-weight:bold; color:#0052CC;'>{fmt_num}%</span>"
                    elif key_str == 'target_percentage':
                        disp = f"{fmt_num}%"
                    elif num > 1_000_000 and not str(k).isdigit():
                         disp = f"{num/1_000_000:,.1f}M"
                    else:
                        disp = fmt_num
                except: disp = val
            cells += f"<td>{disp}</td>"
        rows_html += f"<tr>{cells}</tr>"

    st.markdown(f"""
    <div class="finance-table-container">
        <table class="finance-table">
            <thead><tr>{headers}</tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)
