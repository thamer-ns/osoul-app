import streamlit as st
from datetime import date
from config import APP_NAME, APP_ICON, DEFAULT_COLORS

def render_navbar():
    C = DEFAULT_COLORS
    u = st.session_state.get('username', 'مستثمر')
    
    # الصندوق العلوي (اللوقو واسم المستخدم)
    st.markdown(f"""
    <div class="navbar-box">
        <div style="display: flex; align-items: center; gap: 15px;">
            <div style="font-size: 2.2rem;">{APP_ICON}</div>
            <div>
                <h2 style="margin: 0; color: {C['primary']} !important; font-weight: 900; font-size: 1.5rem;">{APP_NAME}</h2>
                <span style="font-size: 0.8rem; color: {C['sub_text']}; font-weight: 600;">بوابتك الذكية للاستثمار</span>
            </div>
        </div>
        <div style="text-align: left; background-color: {C['page_bg']}; padding: 8px 15px; border-radius: 12px;">
            <div style="color: {C['primary']}; font-weight: 800; font-size: 0.9rem;">{u}</div>
            <div style="font-weight: 700; color: {C['sub_text']}; font-size: 0.8rem; direction: ltr;">{date.today().strftime('%Y-%m-%d')}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # أزرار التنقل (بتصميم أنيق)
    cols = st.columns(9, gap="small")
    # تم إعادة ترتيب الأزرار وإضافة "المحفظة" كخيار جامع إذا أردت
    menu_items = [
        ('الرئيسية', 'home'), ('مضاربة', 'spec'), ('استثمار', 'invest'), 
        ('صكوك', 'sukuk'), ('السيولة', 'cash'), ('التحليل', 'analysis'),
        ('المختبر', 'backtest'), ('إعدادات', 'settings'), ('خروج', 'logout')
    ]
    
    for col, (label, key) in zip(cols, menu_items):
        active = (st.session_state.get('page') == key)
        # نستخدم type="primary" للزر النشط فقط
        if col.button(label, key=f"nav_{key}", type="primary" if active else "secondary", use_container_width=True):
            if key == 'logout':
                from security import logout
                logout()
            else:
                st.session_state.page = key
                st.rerun()
    st.markdown("---")

def render_kpi(label, value, color_condition=None):
    C = DEFAULT_COLORS
    val_c = C['main_text']
    
    if color_condition == "blue": val_c = C['primary']
    elif isinstance(color_condition, (int, float)):
        val_c = C['success'] if color_condition >= 0 else C['danger']
    elif color_condition == "success": val_c = C['success']
    elif color_condition == "danger": val_c = C['danger']
            
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
            
            # 1. معالجة التاريخ
            if 'date' in k and val:
                disp = str(val)[:10]

            # 2. معالجة الحالة (Status Badge)
            elif k == 'status':
                if is_closed:
                    bg, fg, txt = ("#F3F4F6", "#4B5563", "مغلقة")
                else:
                    bg, fg, txt = ("#DCFCE7", "#166534", "مفتوحة")
                disp = f"<span style='background:{bg}; color:{fg}; padding:4px 10px; border-radius:12px; font-size:0.75rem; font-weight:800;'>{txt}</span>"
            
            # 3. معالجة الأرقام والنسب
            elif k in ['gain', 'gain_pct', 'daily_change', 'return_pct']:
                if is_closed and k == 'daily_change':
                    disp = "<span style='color:#9CA3AF'>-</span>"
                else:
                    try:
                        num_val = float(val)
                        c = C['success'] if num_val >= 0 else C['danger']
                        suffix = "%" if 'pct' in k or 'change' in k else ""
                        fmt = "{:,.2f}".format(num_val)
                        disp = f"<span style='color:{c}; direction:ltr; font-weight:bold;'>{fmt}{suffix}</span>"
                    except: disp = val

            # 4. معالجة العملات والأرقام العادية
            elif k in ['market_value', 'total_cost', 'entry_price', 'current_price', 'year_high', 'year_low', 'amount']:
                try: disp = "{:,.2f}".format(float(val))
                except: disp = val
            
            # 5. معالجة الكميات (بدون فواصل عشرية)
            elif k in ['quantity']:
                try: disp = "{:,.0f}".format(float(val))
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
