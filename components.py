import streamlit as st
from config import APP_NAME, APP_ICON

def render_navbar():
    if 'custom_colors' not in st.session_state:
        from config import DEFAULT_COLORS
        st.session_state.custom_colors = DEFAULT_COLORS.copy()
    
    with st.container():
        c_logo, c_nav, c_user = st.columns([1.5, 6, 1.5], gap="small")
        with c_logo:
            st.markdown(f"""<div style="display:flex;align-items:center;gap:8px;padding-top:5px;"><div class="app-logo-box">{APP_ICON}</div><div><div class="logo-text">{APP_NAME}</div></div></div>""", unsafe_allow_html=True)
        with c_nav:
            cols = st.columns(7, gap="small")
            nav_items = [("الرئيسة", "home"), ("مضاربة", "spec"), ("استثمار", "invest"), ("صكوك", "sukuk"), ("تحليل", "analysis"), ("سيولة", "cash"), ("تحديث", "update")]
            for col, (label, key) in zip(cols, nav_items):
                is_active = (st.session_state.get('page') == key)
                with col:
                    btn_type = "primary" if is_active else "secondary"
                    if st.button(label, key=f"nav_{key}", type=btn_type, use_container_width=True):
                        if key == "update": st.session_state.page = "update"
                        else: st.session_state.page = key
                        st.rerun()
        with c_user:
            with st.popover("👤 المستثمر", use_container_width=True):
                if st.button("⚙️  الإعدادات", key="u_set", use_container_width=True): st.session_state.page = "settings"; st.rerun()
                if st.button("📥  إضافة عملية", key="u_add", use_container_width=True): st.session_state.page = "add"; st.rerun()
                st.markdown("---")
                if st.button("تسجيل الخروج", key="u_out", type="primary", use_container_width=True): st.session_state.page = "logout"; st.rerun()
    st.markdown("---")

def render_kpi(label, value, color_condition=None, help_text=None):
    C = st.session_state.custom_colors
    val_c = C['main_text']
    if color_condition == "blue": val_c = C['primary']
    elif color_condition == "success": val_c = C['success']
    elif isinstance(color_condition, (int, float)): val_c = C['success'] if color_condition >= 0 else C['danger']
    
    tooltip = f'title="{help_text}"' if help_text else ''
    st.markdown(f"""<div class="kpi-box" {tooltip}><div style="color:{C['sub_text']};font-size:0.85rem;font-weight:700;margin-bottom:5px;">{label}</div><div class="kpi-value" style="color:{val_c}!important;direction:ltr;">{value}</div></div>""", unsafe_allow_html=True)

def render_table(df, cols_def):
    """
    محرك الجداول الموحد: يقوم برسم أي بيانات تأتيه بتصميم ثابت وأنيق.
    """
    if df.empty:
        st.info("لا توجد بيانات للعرض")
        return

    # بناء رأس الجدول
    headers = ""
    for _, title in cols_definition:
        headers += f"<th>{title}</th>" if cols_definition else ""
    
    # إذا تم تمرير cols_def كقائمة عادية، نعالجها
    if cols_def and isinstance(cols_def[0], tuple):
        headers = "".join([f"<th>{label}</th>" for _, label in cols_def])
        col_keys = [k for k, _ in cols_def]
    else:
        # fallback
        headers = "".join([f"<th>{c}</th>" for c in df.columns])
        col_keys = df.columns

    rows_html = ""
    for _, row in df.iterrows():
        cells = ""
        # التحقق من حالة الإغلاق لتغيير الخلفية قليلاً (تمييز بصري)
        is_closed = str(row.get('status', '')).lower() in ['close', 'sold', 'مغلقة']
        
        for k in col_keys:
            val = row.get(k, "-")
            disp = val
            key_str = str(k).lower() # تحويل المفتاح لنص دائماً لتجنب الأخطاء
            
            # --- منطق التنسيق ---
            
            # 1. التواريخ
            if 'date' in key_str and val:
                disp = str(val)[:10]
            
            # 2. الحالة (Status Badge)
            elif key_str == 'status':
                if not is_closed:
                    disp = f"<span style='background:#E3FCEF; color:#006644; padding:2px 8px; border-radius:4px; font-size:0.8rem;'>مفتوحة</span>"
                else:
                    disp = f"<span style='background:#DFE1E6; color:#42526E; padding:2px 8px; border-radius:4px; font-size:0.8rem;'>مغلقة</span>"
            
            # 3. الأرقام والعملات
            elif isinstance(val, (int, float)) or (isinstance(val, str) and val.replace('.','',1).isdigit()):
                try:
                    num = float(val)
                    fmt_num = "{:,.2f}".format(num)
                    
                    # تلوين النسب والأرباح
                    if key_str in ['gain', 'gain_pct', 'net_profit', 'roi_pct', 'daily_change', 'change']:
                        color = "#006644" if num >= 0 else "#DE350B" # الأخضر والأحمر المعتمد
                        suffix = "%" if 'pct' in key_str or 'change' in key_str else ""
                        weight = "bold" if key_str in ['gain', 'gain_pct'] else "600"
                        
                        # حالة خاصة: إذا كانت الصفقة مغلقة، لا تلون التغير اليومي
                        if is_closed and key_str == 'daily_change':
                            disp = "<span style='color:#9CA3AF'>-</span>"
                        else:
                            disp = f"<span style='color:{color}; font-weight:{weight}; direction:ltr;'>{fmt_num}{suffix}</span>"
                    
                    # تلوين الأوزان (القطاعات)
                    elif key_str == 'current_weight':
                        disp = f"<span style='font-weight:bold; color:#0052CC;'>{fmt_num}%</span>"
                    
                    elif key_str == 'target_percentage':
                        disp = f"{fmt_num}%"

                    # تنسيق الملايين (للقوائم المالية)
                    # الشرط: الرقم كبير + اسم العمود ليس سنة (لتجنب تنسيق سنة 2024 كرقم)
                    elif num > 1_000_000 and not str(k).isdigit():
                         disp = f"{num/1_000_000:,.1f}M"
                    
                    else:
                        disp = fmt_num
                except: disp = val
            
            cells += f"<td>{disp}</td>"
        rows_html += f"<tr>{cells}</tr>"

    # الحاوية التي تطبق التصميم من config.py
    st.markdown(f"""
    <div class="finance-table-container">
        <table class="finance-table">
            <thead><tr>{headers}</tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)
