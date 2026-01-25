import streamlit as st
import pandas as pd
from datetime import date
from config import APP_NAME, APP_ICON, DEFAULT_COLORS

def safe_fmt(val, suffix=""):
    if val is None or pd.isna(val) or val == "": return "-"
    try:
        f_val = float(val)
        return f"{f_val:,.2f}{suffix}"
    except:
        return str(val)

def handle_menu_selection():
    """دالة لمعالجة القائمة المنسدلة ومنع التعليق"""
    choice = st.session_state.get("user_menu_key")
    if choice == "➕ إضافة صفقة":
        st.session_state.page = 'add'
    elif choice == "🧪 المختبر":
        st.session_state.page = 'backtest'
    elif choice == "⚙️ الإعدادات":
        st.session_state.page = 'settings'
    elif choice == "🚪 خروج":
        st.session_state.clear()
        st.rerun()
    
    # حيلة مهمة: نعيد القيمة للافتراضي لكي لا يعلق
    # لا يمكن تغيير القيمة مباشرة، لكن الاعتماد على التغيير (Change) يكفي

def render_navbar():
    if 'custom_colors' not in st.session_state:
        from config import DEFAULT_COLORS
        C = DEFAULT_COLORS
    else:
        C = st.session_state.custom_colors
        
    u = st.session_state.get('username', 'مستثمر')
    
    # 1. الهيدر
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

    # 2. القوائم
    c_menu, c_user = st.columns([3, 1])
    
    with c_menu:
        # القوائم الرئيسية كأزرار (أضمن وأسرع)
        cols = st.columns(6)
        labels = ['الرئيسية', 'مضاربة', 'استثمار', 'صكوك', 'السيولة', 'التحليل']
        keys = ['home', 'spec', 'invest', 'sukuk', 'cash', 'analysis']
        
        for i, (col, label, key) in enumerate(zip(cols, labels, keys)):
            active = (st.session_state.get('page') == key)
            btn_type = "primary" if active else "secondary"
            if col.button(label, key=f"nav_{key}", type=btn_type, use_container_width=True):
                st.session_state.page = key
                st.rerun()

    with c_user:
        # القائمة المنسدلة (تم حل مشكلة التعليق باستخدام مفتاح فريد وعدم الفرض)
        # نستخدم label مرئي بالعربي لمنع ظهور الإنجليزي
        opts = ["القائمة...", "➕ إضافة صفقة", "🧪 المختبر", "⚙️ الإعدادات", "🚪 خروج"]
        
        # نستخدم on_change للتنقل الفوري
        st.selectbox(
            "خيارات إضافية", # عنوان عربي صريح
            options=opts,
            key="user_menu_key",
            on_change=handle_menu_selection, # الاستدعاء عند التغيير فقط
            label_visibility="visible" # إظهار العنوان لمنع مشاكل المتصفح
        )

    st.markdown("---")

def render_kpi(label, value, color_condition=None):
    C = DEFAULT_COLORS
    val_c = C['main_text']
    if color_condition == "blue": val_c = C['primary']
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
    try: price, change = float(price), float(change)
    except: price, change = 0.0, 0.0
    color = C['success'] if change >= 0 else C['danger']
    bg_color = "#DCFCE7" if change >= 0 else "#FEE2E2"
    st.markdown(f"""
    <div style="background-color: {C['card_bg']}; padding: 15px; border-radius: 14px; border: 1px solid {C['border']}; margin-bottom: 10px;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
            <div style="font-weight: 800; color: {C['primary']};">{symbol}</div>
            <div style="background-color: {bg_color}; color: {color}; padding: 2px 8px; border-radius: 6px; font-weight: 800; direction: ltr;">{change:.2f}%</div>
        </div>
        <div style="font-size: 0.8rem; color: {C['sub_text']};">{name}</div>
        <div style="font-size: 1.4rem; font-weight: 900; color: {C['main_text']}; direction: ltr;">{price:,.2f}</div>
    </div>""", unsafe_allow_html=True)

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
            val = row.get(k)
            if pd.isna(val) or val == "" or val is None or (k in ['year_high', 'year_low', 'prev_close'] and float(val or 0)==0):
                disp = "<span style='color:#ccc; font-size:0.8rem;'>غير موجود</span>"
            else:
                disp = val
                if 'date' in k: disp = f"<span style='color:{C['sub_text']}; font-family:monospace;'>{str(val)[:10]}</span>"
                elif k == 'status':
                    bg, fg, txt = ("#F3F4F6", "#4B5563", "مغلقة") if is_closed else ("#DCFCE7", "#166534", "مفتوحة")
                    disp = f"<span style='background:{bg}; color:{fg}; padding:4px 10px; border-radius:8px; font-size:0.75rem; font-weight:800;'>{txt}</span>"
                elif isinstance(val, (int, float)):
                    f_val = f"{val:,.2f}"
                    if k in ['gain', 'gain_pct', 'daily_change', 'return_pct', 'net_sales', 'realized_gain']:
                        c = C['success'] if val >= 0 else C['danger']
                        suffix = "%" if 'pct' in k or 'change' in k else ""
                        disp = f"<span style='color:{c}; direction:ltr; font-weight:bold;'>{f_val}{suffix}</span>"
                    elif k == 'weight':
                        disp = f"<span style='color:{C['primary']}; direction:ltr; font-weight:bold;'>{f_val}%</span>"
                    elif k == 'quantity':
                        disp = f"<span style='font-weight:800;'>{val:,.0f}</span>"
                    else:
                        disp = f"<span style='direction:ltr; font-weight:600;'>{f_val}</span>"
            cells += f"<td>{disp}</td>"
        rows_html += f"<tr>{cells}</tr>"
    st.markdown(f"""<div class="finance-table-container"><div style="overflow-x: auto;"><table class="finance-table"><thead><tr>{headers}</tr></thead><tbody>{rows_html}</tbody></table></div></div>""", unsafe_allow_html=True)
