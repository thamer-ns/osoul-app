import streamlit as st
from datetime import date
from config import APP_NAME, APP_ICON, DEFAULT_COLORS

# دالة تقريب الأرقام (التي تحافظ على نظافة الجدول)
def safe_fmt(val, suffix=""):
    if val is None or pd.isna(val) or val == "": return "-"
    try:
        f_val = float(val)
        return f"{f_val:,.2f}{suffix}"
    except:
        return str(val)

def render_navbar():
    if 'custom_colors' not in st.session_state:
        st.session_state.custom_colors = DEFAULT_COLORS.copy()
    C = st.session_state.custom_colors
    u = st.session_state.get('username', 'مستثمر')

    # 1. الهيدر الجميل (HTML)
    st.markdown(f"""
    <div class="navbar-container">
        <div style="display: flex; align-items: center; gap: 15px;">
            <div style="font-size: 2.5rem; background: #EFF6FF; width:55px; height:55px; display:flex; align-items:center; justify-content:center; border-radius:14px;">{APP_ICON}</div>
            <div>
                <h2 style="margin: 0; color: {C['primary']} !important; font-weight: 900; font-size: 1.5rem;">{APP_NAME}</h2>
                <span style="font-size: 0.85rem; color: {C['sub_text']}; font-weight: 600;">محفظتك الاستثمارية الذكية</span>
            </div>
        </div>
        <div style="text-align: left; background-color: {C['page_bg']}; padding: 8px 18px; border-radius: 12px; border:1px solid {C['border']};">
            <div style="color: {C['main_text']}; font-weight: 800; font-size: 0.9rem;">👋 {u}</div>
            <div style="font-weight: 700; color: {C['sub_text']}; font-size: 0.8rem; direction: ltr;">{date.today().strftime('%Y-%m-%d')}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 2. القائمة المدمجة (أزرار + قائمة منسدلة)
    # نقسم العمود: 8 أجزاء للقوائم الرئيسية، 3 أجزاء للقائمة الشخصية المنسدلة
    c_main, c_user = st.columns([3, 1])
    
    with c_main:
        # القوائم الرئيسية (أزرار بجانب بعض)
        cols = st.columns(7)
        labels = ['الرئيسية', 'مضاربة', 'استثمار', 'صكوك', 'السيولة', 'التحليل', 'المختبر']
        keys = ['home', 'spec', 'invest', 'sukuk', 'cash', 'analysis', 'backtest']
        
        for i, (col, label, key) in enumerate(zip(cols, labels, keys)):
            active = (st.session_state.get('page') == key)
            if col.button(label, key=f"nav_{key}", type="primary" if active else "secondary", use_container_width=True):
                st.session_state.page = key
                st.rerun()

    with c_user:
        # القائمة المنسدلة (تجمع الإعدادات والأدوات والإضافة والخروج)
        # نستخدم selectbox كقائمة تنقل
        action = st.selectbox(
            "القائمة الشخصية", # العنوان مخفي بالـ CSS
            options=["⚙️ خيارات الحساب", "➕ إضافة صفقة", "🛠️ الأدوات", "⚙️ الإعدادات", "🚪 تسجيل خروج"],
            key="user_menu_select",
            label_visibility="collapsed"
        )
        
        # منطق التوجيه عند الاختيار
        if action == "➕ إضافة صفقة" and st.session_state.get('page') != 'add':
            st.session_state.page = 'add'; st.rerun()
        elif action == "🛠️ الأدوات" and st.session_state.get('page') != 'tools':
            st.session_state.page = 'tools'; st.rerun()
        elif action == "⚙️ الإعدادات" and st.session_state.get('page') != 'settings':
            st.session_state.page = 'settings'; st.rerun()
        elif action == "🚪 تسجيل خروج":
            from security import logout; logout()

    st.markdown("---")

def render_kpi(label, value, color_condition=None):
    C = DEFAULT_COLORS
    val_c = C['main_text']
    
    if color_condition == "blue": val_c = C['primary']
    elif color_condition == "success": val_c = C['success']
    elif color_condition == "danger": val_c = C['danger']
    elif isinstance(color_condition, (int, float)):
        val_c = C['success'] if color_condition >= 0 else C['danger']
            
    st.markdown(f"""
    <div class="kpi-box">
        <div style="color:{C['sub_text']}; font-size:0.9rem; font-weight:800; margin-bottom:8px;">{label}</div>
        <div class="kpi-value" style="color: {val_c} !important;">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def render_ticker_card(symbol, name, price, change):
    C = DEFAULT_COLORS
    try: price = float(price); change = float(change)
    except: price = 0.0; change = 0.0

    color = C['success'] if change >= 0 else C['danger']
    arrow = "▲" if change >= 0 else "▼"
    bg = "#DCFCE7" if change >= 0 else "#FEE2E2"

    st.markdown(f"""
    <div style="background-color: {C['card_bg']}; padding: 15px; border-radius: 14px; border: 1px solid {C['border']}; margin-bottom: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.02); transition: transform 0.2s;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
            <div style="font-weight: 800; color: {C['primary']}; font-size: 1rem;">{symbol}</div>
            <div style="background-color: {bg}; color: {color}; padding: 3px 8px; border-radius: 6px; font-weight: 800; font-size: 0.8rem; direction: ltr;">
                {change:.2f}% {arrow}
            </div>
        </div>
        <div style="font-size: 0.85rem; color: {C['sub_text']}; margin-bottom: 5px; font-weight: 600;">{name}</div>
        <div style="font-size: 1.5rem; font-weight: 900; color: {C['main_text']}; direction: ltr;">{price:,.2f}</div>
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
            val = row.get(k)
            
            # --- معالجة القيم الفارغة ---
            if pd.isna(val) or val == "" or val is None:
                disp = "<span style='color:#CBD5E1; font-style:italic; font-size:0.85rem;'>غير موجود</span>"
            else:
                disp = val
                
                # تنسيقات خاصة
                if 'date' in k: 
                    disp = f"<span style='color:{C['sub_text']}; font-family:monospace; font-weight:600;'>{str(val)[:10]}</span>"
                
                elif k == 'status':
                    bg, fg, txt = ("#F1F5F9", "#64748B", "مغلقة") if is_closed else ("#DCFCE7", "#166534", "مفتوحة")
                    disp = f"<span style='background:{bg}; color:{fg}; padding:5px 12px; border-radius:8px; font-size:0.8rem; font-weight:800;'>{txt}</span>"
                
                elif isinstance(val, (int, float)):
                    # التقريب + التلوين
                    f_val = f"{val:,.2f}"
                    if k in ['gain', 'gain_pct', 'daily_change', 'return_pct', 'net_sales', 'realized_gain', 'amount']:
                        c = C['success'] if val >= 0 else C['danger']
                        suffix = "%" if 'pct' in k or 'change' in k else ""
                        disp = f"<span style='color:{c}; direction:ltr; font-weight:bold;'>{f_val}{suffix}</span>"
                    elif k == 'quantity':
                        disp = f"<span style='font-weight:800;'>{val:,.0f}</span>"
                    else:
                        disp = f"<span style='direction:ltr; font-weight:600;'>{f_val}</span>"

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
