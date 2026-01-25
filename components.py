import streamlit as st
from datetime import date
from config import APP_NAME, APP_ICON, DEFAULT_COLORS

# دالة تقريب الأرقام
def safe_fmt(val, suffix=""):
    try:
        if val is None or val == "": return "-"
        f_val = float(val)
        return f"{f_val:,.2f}{suffix}"
    except:
        return str(val)

def render_navbar():
    C = st.session_state.custom_colors
    u = st.session_state.get('username', 'مستثمر')
    
    # الهيدر الجميل
    st.markdown(f"""
    <div class="nav-container">
        <div style="display: flex; align-items: center; gap: 15px;">
            <div style="font-size: 2.5rem; background: #EFF6FF; width:60px; height:60px; display:flex; align-items:center; justify-content:center; border-radius:15px;">{APP_ICON}</div>
            <div>
                <h1 style="margin:0; font-size:1.6rem; color:{C['primary']}; font-weight:900;">{APP_NAME}</h1>
                <span style="font-size:0.85rem; color:{C['sub_text']}; font-weight:600;">بوابتك الذكية للاستثمار</span>
            </div>
        </div>
        <div style="text-align: left; background:{C['page_bg']}; padding:8px 15px; border-radius:10px; border:1px solid {C['border']};">
            <div style="font-weight:800; color:{C['main_text']}; font-size:0.9rem;">👤 {u}</div>
            <div style="font-weight:600; color:{C['sub_text']}; font-size:0.8rem; direction:ltr;">{date.today().strftime('%Y-%m-%d')}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # القائمة
    cols = st.columns(11, gap="small")
    menu = [
        ('الرئيسية', 'home'), ('نبض السوق', 'pulse'), ('مضاربة', 'spec'), 
        ('استثمار', 'invest'), ('صكوك', 'sukuk'), ('السيولة', 'cash'), 
        ('التحليل', 'analysis'), ('المختبر', 'backtest'), ('أدوات', 'tools'),
        ('إعدادات', 'settings'), ('خروج', 'logout')
    ]
    
    for col, (label, key) in zip(cols, menu):
        active = (st.session_state.get('page') == key)
        if col.button(label, key=f"nav_{key}", type="primary" if active else "secondary"):
            if key == 'logout': 
                st.session_state.clear(); st.rerun()
            else: 
                st.session_state.page = key; st.rerun()
    st.markdown("---")

def render_kpi(label, value, color_condition=None):
    C = DEFAULT_COLORS
    val_color = C['main_text']
    
    if color_condition == "blue": val_color = C['primary']
    elif color_condition == "success": val_color = C['success']
    elif color_condition == "danger": val_color = C['danger']
    elif isinstance(color_condition, (int, float)):
        val_color = C['success'] if color_condition >= 0 else C['danger']
            
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value" style="color: {val_color} !important;">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def render_ticker_card(symbol, name, price, change):
    C = DEFAULT_COLORS
    try: p, c = float(price), float(change)
    except: p, c = 0.0, 0.0
    
    col = C['success'] if c >= 0 else C['danger']
    arr = "▲" if c >= 0 else "▼"
    bg = "#DCFCE7" if c >= 0 else "#FEE2E2"
    
    st.markdown(f"""
    <div style="background:{C['card_bg']}; padding:15px; border-radius:14px; border:1px solid {C['border']}; margin-bottom:10px; box-shadow:0 2px 5px rgba(0,0,0,0.02);">
        <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
            <div style="font-weight:800; font-size:1.1rem; color:{C['primary']};">{symbol}</div>
            <div style="background:{bg}; color:{col}; padding:3px 8px; border-radius:6px; font-weight:800; font-size:0.8rem; direction:ltr;">{c:.2f}% {arr}</div>
        </div>
        <div style="font-size:0.85rem; color:{C['sub_text']}; margin-bottom:5px;">{name}</div>
        <div style="font-size:1.5rem; font-weight:900; color:{C['main_text']}; text-align:left; direction:ltr;">{p:,.2f}</div>
    </div>
    """, unsafe_allow_html=True)

def render_table(df, cols_def):
    if df.empty: st.info("لا توجد بيانات"); return
    C = DEFAULT_COLORS
    
    headers = "".join([f"<th>{label}</th>" for _, label in cols_def])
    rows = ""
    
    for _, row in df.iterrows():
        cells = ""
        is_closed = str(row.get('status', '')).lower() in ['close', 'sold', 'مغلقة']
        
        for k, _ in cols_def:
            val = row.get(k, "-")
            disp = safe_fmt(val) # استخدام دالة التقريب الموحدة
            
            if 'date' in k: disp = str(val)[:10]
            elif k == 'status':
                bg, txt = ("#F3F4F6", "مغلقة") if is_closed else ("#DCFCE7", "مفتوحة")
                disp = f"<span style='background:{bg}; padding:4px 10px; border-radius:8px; font-size:0.8rem;'>{txt}</span>"
            elif 'pct' in k or 'gain' in k or 'change' in k:
                try:
                    n = float(val)
                    c = C['success'] if n >= 0 else C['danger']
                    disp = f"<span style='color:{c}; font-weight:bold; direction:ltr;'>{disp}</span>"
                except: pass
                
            cells += f"<td>{disp}</td>"
        rows += f"<tr>{cells}</tr>"
        
    st.markdown(f"""
    <div style="overflow-x:auto;">
        <table class="finance-table">
            <thead><tr>{headers}</tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)
