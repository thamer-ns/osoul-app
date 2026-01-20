import streamlit as st
from config import APP_NAME, APP_ICON

def render_navbar():
    if 'custom_colors' not in st.session_state:
        from config import DEFAULT_COLORS
        st.session_state.custom_colors = DEFAULT_COLORS.copy()
    
    current_user = st.session_state.get('username', 'المستثمر')

    with st.container():
        c_logo, c_nav, c_user = st.columns([1.5, 5.5, 1.5], gap="small")
        with c_logo:
            st.markdown(f"""<div style="display:flex;align-items:center;gap:8px;padding-top:5px;"><div class="app-logo-box">{APP_ICON}</div><div><div class="logo-text">{APP_NAME}</div></div></div>""", unsafe_allow_html=True)
        with c_nav:
            cols = st.columns(6, gap="small")
            nav_items = [("الرئيسة", "home"), ("مضاربة", "spec"), ("استثمار", "invest"), ("تحليل", "analysis"), ("إضافة", "add"), ("أدوات", "tools")]
            for col, (label, key) in zip(cols, nav_items):
                is_active = (st.session_state.get('page') == key)
                with col:
                    if st.button(label, key=f"nav_{key}", type="primary" if is_active else "secondary", use_container_width=True):
                        st.session_state.page = key; st.rerun()
        with c_user:
            with st.popover(current_user, use_container_width=True):
                if st.button("⚙️  الإعدادات", key="u_set", use_container_width=True): st.session_state.page = "settings"; st.rerun()
                if st.button("🔄 تحديث أسعار", key="u_upd", use_container_width=True): st.session_state.page = "update"; st.rerun()
                st.markdown("---")
                if st.button("خروج", key="u_out", type="primary", use_container_width=True): st.session_state.page = "logout"; st.rerun()
    st.markdown("---")

def render_kpi(label, value, color_condition=None, help_text=None):
    C = st.session_state.custom_colors
    val_c = C['main_text']
    if color_condition == "blue": val_c = C['primary']
    elif color_condition == "success": val_c = C['success']
    elif isinstance(color_condition, (int, float)): val_c = C['success'] if color_condition >= 0 else C['danger']
    
    tooltip = f'title="{help_text}"' if help_text else ''
    st.markdown(f"""<div class="kpi-box" {tooltip}><div style="color:{C['sub_text']};font-size:0.8rem;font-weight:700;margin-bottom:5px;">{label}</div><div class="kpi-value" style="color:{val_c}!important;direction:ltr;">{value}</div></div>""", unsafe_allow_html=True)

def render_table(df, cols_def):
    if df.empty: st.info("لا توجد بيانات"); return
    C = st.session_state.custom_colors
    headers = "".join([f"<th>{label}</th>" for _, label in cols_def])
    rows_html = ""
    for _, row in df.iterrows():
        cells = ""
        for k, _ in cols_def:
            val = row.get(k, "-")
            disp = val
            if isinstance(val, (int, float)):
                 disp = f"{val:,.2f}"
                 if 'pct' in k or 'percentage' in k: disp += "%"
            cells += f"<td>{disp}</td>"
        rows_html += f"<tr>{cells}</tr>"
    st.markdown(f"""<div style="overflow-x: auto;"><table class="finance-table"><thead><tr>{headers}</tr></thead><tbody>{rows_html}</tbody></table></div>""", unsafe_allow_html=True)
