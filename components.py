import streamlit as st
from config import APP_NAME, APP_ICON, DEFAULT_COLORS

def render_navbar():
    C = DEFAULT_COLORS
    with st.container():
        c1, c2, c3 = st.columns([1.5, 6, 1.5])
        with c1:
            st.markdown(f"<h3 style='margin:0; color:{C['primary']};'>{APP_ICON} {APP_NAME}</h3>", unsafe_allow_html=True)
        
        with c2:
            # القائمة الكاملة مع الأيقونات
            menu = [
                ("🏠 الرئيسية", "home"), ("💓 نبض", "pulse"), ("⚡ مضاربة", "spec"), 
                ("🌳 استثمار", "invest"), ("📜 صكوك", "sukuk"), ("📊 تحليل", "analysis"), 
                ("💵 سجلات", "cash"), ("🧪 مختبر", "backtest"), ("🛠️ أدوات", "tools")
            ]
            cols = st.columns(len(menu))
            for col, (title, page) in zip(cols, menu):
                with col:
                    active = st.session_state.get('page') == page
                    btn_type = "primary" if active else "secondary"
                    if st.button(title, key=f"nav_{page}", type=btn_type, use_container_width=True):
                        st.session_state.page = page
                        st.rerun()
        
        with c3:
            # قائمة المستخدم السريعة
            with st.popover(f"👤 {st.session_state.get('username', 'زائر')}"):
                if st.button("➕ صفقة جديدة", use_container_width=True): st.session_state.page = 'add'; st.rerun()
                if st.button("⚙️ الإعدادات", use_container_width=True): st.session_state.page = 'settings'; st.rerun()
                if st.button("🔄 تحديث الأسعار", use_container_width=True): st.session_state.page = 'update'; st.rerun()
                st.divider()
                if st.button("🚪 خروج", use_container_width=True): 
                    st.session_state.clear(); st.rerun()
    st.markdown("---")

def render_kpi(label, value, color_condition=None):
    C = DEFAULT_COLORS
    c = C['main_text']
    if color_condition == 'blue': c = C['primary']
    elif isinstance(color_condition, (int, float)):
        c = C['success'] if color_condition >= 0 else C['danger']
        
    st.markdown(f"""
    <div class="kpi-box">
        <div style="color:{C['sub_text']}; font-size:0.85rem; font-weight:600; margin-bottom:5px;">{label}</div>
        <div style="color:{c}; font-size:1.4rem; font-weight:800; direction:ltr;">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def render_ticker_card(symbol, name, price, change):
    C = DEFAULT_COLORS
    color = C['success'] if change >= 0 else C['danger']
    arrow = "🔼" if change >= 0 else "🔽"
    
    st.markdown(f"""
    <div class="ticker-card">
        <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
            <span style="font-weight:bold; color:{C['primary']};">{symbol}</span>
            <span style="font-size:0.8rem; color:{C['sub_text']};">{name}</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-size:1.2rem; font-weight:bold;">{price:,.2f}</span>
            <span style="color:{color}; font-weight:bold; font-size:0.9rem; direction:ltr;">{arrow} {change:.2f}%</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_table(df, cols_def):
    if df.empty:
        st.info("لا توجد بيانات للعرض")
        return
    
    C = DEFAULT_COLORS
    headers = "".join([f"<th>{label}</th>" for _, label in cols_def])
    rows_html = ""
    
    for _, row in df.iterrows():
        cells = ""
        is_closed = str(row.get('status', '')).lower() in ['close', 'sold', 'مغلقة']
        for k, _ in cols_def:
            val = row.get(k, "-")
            disp = val
            key_str = str(k).lower()
            
            if 'date' in key_str and val: disp = str(val)[:10]
            elif key_str == 'status':
                disp = f"<span style='color:{C['sub_text']}'>مغلقة</span>" if is_closed else f"<span style='color:{C['success']}'>مفتوحة</span>"
            elif isinstance(val, (int, float)):
                try:
                    num = float(val)
                    if key_str in ['gain', 'gain_pct', 'daily_change', 'change']:
                        c = C['success'] if num >= 0 else C['danger']
                        suffix = "%" if 'pct' in key_str else ""
                        disp = f"<span style='color:{c}; direction:ltr; font-weight:bold;'>{num:,.2f}{suffix}</span>"
                    else:
                        disp = f"{num:,.2f}"
                except: disp = val
            cells += f"<td>{disp}</td>"
        rows_html += f"<tr>{cells}</tr>"

    st.markdown(f"""
    <div class="finance-table-container">
        <div style="overflow-x: auto;">
            <table class="finance-table">
                <thead><tr>{headers}</tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
        </div>
    </div>
    """, unsafe_allow_html=True)
