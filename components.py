import streamlit as st
from datetime import date
from config import APP_NAME, APP_ICON, DEFAULT_COLORS

def render_navbar():
    if 'custom_colors' not in st.session_state:
        from config import DEFAULT_COLORS
        C = DEFAULT_COLORS
    else:
        C = st.session_state.custom_colors
        
    u = st.session_state.get('username', 'مستثمر')
    
    # الناف بار بتصميم الصندوق العائم
    st.markdown(f"""
    <div style="background-color: {C['card_bg']}; padding: 15px 25px; border-radius: 16px; border: 1px solid {C['border']}; margin-bottom: 25px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
        <div style="display: flex; align-items: center; gap: 15px;">
            <div style="font-size: 2.2rem; background: #EFF6FF; width:50px; height:50px; display:flex; align-items:center; justify-content:center; border-radius:12px;">{APP_ICON}</div>
            <div>
                <h2 style="margin: 0; color: {C['primary']} !important; font-weight: 800; font-size: 1.4rem;">{APP_NAME}</h2>
                <span style="font-size: 0.8rem; color: {C['sub_text']}; font-weight: 600;">بوابتك الذكية للاستثمار</span>
            </div>
        </div>
        <div style="text-align: left; background-color: {C['page_bg']}; padding: 8px 16px; border-radius: 10px; border:1px solid {C['border']};">
            <div style="color: {C['main_text']}; font-weight: 700; font-size: 0.85rem;">👤 {u}</div>
            <div style="font-weight: 600; color: {C['sub_text']}; font-size: 0.75rem; direction: ltr;">{date.today().strftime('%Y-%m-%d')}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # القائمة
    cols = st.columns(11, gap="small")
    menu_items = [
        ('الرئيسية', 'home'), ('نبض السوق', 'pulse'), ('مضاربة', 'spec'), 
        ('استثمار', 'invest'), ('صكوك', 'sukuk'), ('السيولة', 'cash'), 
        ('التحليل', 'analysis'), ('المختبر', 'backtest'), ('أدوات', 'tools'),
        ('إعدادات', 'settings'), ('خروج', 'logout')
    ]
    
    for col, (label, key) in zip(cols, menu_items):
        active = (st.session_state.get('page') == key)
        btn_type = "primary" if active else "secondary"
        if col.button(label, key=f"nav_{key}", type=btn_type, use_container_width=True):
            if key == 'logout':
                from security import logout; logout()
            else:
                st.session_state.page = key; st.rerun()
    st.markdown("---")

def render_kpi(label, value, color_condition=None):
    C = DEFAULT_COLORS
    val_c = C['main_text']
    
    # تحديد لون الرقم
    if color_condition == "blue": val_c = C['primary']
    elif color_condition == "success": val_c = C['success']
    elif color_condition == "danger": val_c = C['danger']
    elif isinstance(color_condition, (int, float)):
        val_c = C['success'] if color_condition >= 0 else C['danger']
            
    st.markdown(f"""
    <div class="kpi-box">
        <div style="color:{C['sub_text']}; font-size:0.9rem; font-weight:700; margin-bottom:8px;">{label}</div>
        <div class="kpi-value" style="color: {val_c} !important;">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def render_ticker_card(symbol, name, price, change):
    C = DEFAULT_COLORS
    try:
        price = float(price) if price is not None else 0.0
        change = float(change) if change is not None else 0.0
    except: price = 0.0; change = 0.0

    color = C['success'] if change >= 0 else C['danger']
    arrow = "▲" if change >= 0 else "▼"
    bg_color = "#DCFCE7" if change >= 0 else "#FEE2E2"

    st.markdown(f"""
    <div style="background-color: {C['card_bg']}; padding: 16px; border-radius: 14px; border: 1px solid {C['border']}; margin-bottom: 12px; transition: transform 0.2s;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px;">
            <div>
                <div style="font-weight: 800; color: {C['main_text']}; font-size: 1.1rem;">{symbol}</div>
                <div style="font-size: 0.8rem; color: {C['sub_text']}; font-weight:600;">{name}</div>
            </div>
            <div style="background-color: {bg_color}; color: {color}; padding: 4px 8px; border-radius: 6px; font-weight: 800; font-size: 0.8rem; direction: ltr;">
                {change:.2f}% {arrow}
            </div>
        </div>
        <div style="font-size: 1.6rem; font-weight: 900; color: {C['main_text']}; letter-spacing: -0.5px;">{price:,.2f}</div>
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
        status_val = str(row.get('status', '')).lower()
        is_closed = status_val in ['close', 'sold', 'مغلقة', 'مباعة']
        
        for k, _ in cols_def:
            val = row.get(k, "-")
            disp = val
            
            # تنسيقات مخصصة
            if 'date' in k and val: 
                disp = f"<span style='color:{C['sub_text']}; font-family:monospace;'>{str(val)[:10]}</span>"
            
            elif k == 'status':
                bg, fg, txt = ("#F3F4F6", "#4B5563", "مغلقة") if is_closed else ("#DCFCE7", "#166534", "مفتوحة")
                disp = f"<span style='background:{bg}; color:{fg}; padding:4px 10px; border-radius:8px; font-size:0.75rem; font-weight:800;'>{txt}</span>"
            
            elif k in ['gain', 'gain_pct', 'daily_change', 'return_pct', 'net_sales', 'realized_gain', 'amount']:
                try:
                    num_val = float(val)
                    c = C['success'] if num_val >= 0 else C['danger']
                    suffix = "%" if 'pct' in k or 'change' in k else ""
                    # إضافة سهم للأرباح
                    icon = "↗" if num_val >= 0 else "↘"
                    if 'pct' in k:
                        disp = f"<span style='color:{c}; direction:ltr; font-weight:bold; background:{c}15; padding:2px 6px; border-radius:4px;'>{num_val:,.2f}{suffix}</span>"
                    else:
                        disp = f"<span style='color:{c}; direction:ltr; font-weight:bold;'>{num_val:,.2f}</span>"
                except: disp = val

            elif k in ['market_value', 'total_cost', 'entry_price', 'current_price', 'exit_price']:
                try: disp = f"{float(val):,.2f}"
                except: disp = val
            
            elif k == 'quantity':
                try: disp = f"<span style='font-weight:800;'>{float(val):,.0f}</span>"
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
