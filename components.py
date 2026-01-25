import streamlit as st
from datetime import date
from config import APP_NAME, APP_ICON, DEFAULT_COLORS

def render_navbar():
    C = DEFAULT_COLORS
    u = st.session_state.get('username', 'مستثمر')
    
    # === القائمة الجانبية (Sidebar) ===
    with st.sidebar:
        st.markdown(f"<h2 style='text-align:center; color:{C['primary']}'>{APP_ICON} {APP_NAME}</h2>", unsafe_allow_html=True)
        st.markdown(f"<div style='text-align:center; margin-bottom:20px; color:{C['sub_text']}'>أهلاً، <b>{u}</b></div>", unsafe_allow_html=True)
        
        st.markdown("---")
        
        # القائمة المنسدلة للتنقل
        selected_page = st.radio(
            "تصفح الأقسام:",
            options=['الرئيسية', 'نبض السوق', 'محفظة المضاربة', 'محفظة الاستثمار', 'محفظة الصكوك', 'سجل السيولة', 'التحليل الشامل', 'مختبر الاستراتيجيات', 'الأدوات والحاسبات', 'تسجيل عملية', 'الإعدادات', 'الملف الشخصي'],
            index=0
        )
        
        # خريطة لربط الأسماء العربية بالمفاتيح البرمجية
        page_map = {
            'الرئيسية': 'home',
            'نبض السوق': 'pulse',
            'محفظة المضاربة': 'spec',
            'محفظة الاستثمار': 'invest',
            'محفظة الصكوك': 'sukuk',
            'سجل السيولة': 'cash',
            'التحليل الشامل': 'analysis',
            'مختبر الاستراتيجيات': 'backtest',
            'الأدوات والحاسبات': 'tools',
            'تسجيل عملية': 'add',
            'الإعدادات': 'settings',
            'الملف الشخصي': 'profile'
        }
        
        # تحديث الصفحة
        if st.session_state.get('page') != page_map[selected_page]:
            st.session_state.page = page_map[selected_page]
            st.rerun()
            
        st.markdown("---")
        if st.button("تحديث الأسعار 🔄", use_container_width=True):
            st.session_state.page = 'update'
            st.rerun()
            
        if st.button("تسجيل الخروج 🔒", type="primary", use_container_width=True):
            from security import logout
            logout()

    # === الشريط العلوي (فقط يعرض العنوان والتاريخ) ===
    st.markdown(f"""
    <div style="background-color: {C['card_bg']}; padding: 15px 20px; border-radius: 16px; border: 1px solid {C['border']}; margin-bottom: 25px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 4px 15px rgba(0,0,0,0.03);">
        <div style="display: flex; align-items: center; gap: 10px;">
            <span style="font-size: 1.2rem; font-weight: bold; color: {C['primary']};">{selected_page}</span>
        </div>
        <div style="font-weight: 700; color: {C['sub_text']}; font-size: 0.9rem; direction: ltr;">
            {date.today().strftime('%Y-%m-%d')}
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_kpi(label, value, color_condition=None):
    C = DEFAULT_COLORS
    val_c = C['main_text']
    
    if color_condition == "blue": val_c = C['primary']
    elif isinstance(color_condition, (int, float)):
        val_c = C['success'] if color_condition >= 0 else C['danger']
            
    st.markdown(f"""
    <div class="kpi-box">
        <div style="color:{C['sub_text']}; font-size:0.85rem; font-weight:600; margin-bottom:5px;">{label}</div>
        <div class="kpi-value" style="color: {val_c} !important;">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def render_table(df, cols_def):
    if df.empty:
        st.info("لا توجد بيانات للعرض")
        return

    headers = "".join([f"<th>{label}</th>" for _, label in cols_def])
    rows_html = ""
    
    for _, row in df.iterrows():
        cells = ""
        status_val = str(row.get('status', '')).lower()
        is_closed = status_val in ['close', 'sold', 'مغلقة', 'مباعة']
        
        for k, _ in cols_def:
            val = row.get(k, "-")
            disp = val
            
            if 'date' in k and val: disp = str(val)[:10]
            elif k == 'status':
                bg, fg, txt = ("#F3F4F6", "#4B5563", "مغلقة") if is_closed else ("#DCFCE7", "#166534", "مفتوحة")
                disp = f"<span style='background:{bg}; color:{fg}; padding:4px 10px; border-radius:12px; font-size:0.75rem; font-weight:800;'>{txt}</span>"
            elif k in ['gain', 'gain_pct', 'daily_change', 'return_pct']:
                try:
                    num_val = float(val)
                    c = DEFAULT_COLORS['success'] if num_val >= 0 else DEFAULT_COLORS['danger']
                    suffix = "%" if 'pct' in k or 'change' in k else ""
                    disp = f"<span style='color:{c}; direction:ltr; font-weight:bold;'>{num_val:,.2f}{suffix}</span>"
                except: disp = val
            elif k in ['market_value', 'total_cost', 'entry_price', 'current_price', 'amount']:
                try: disp = f"{float(val):,.2f}"
                except: disp = val
            elif k == 'quantity':
                try: disp = f"{float(val):,.0f}"
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
