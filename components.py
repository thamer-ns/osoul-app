import streamlit as st
from config import APP_NAME, APP_ICON

def render_navbar():
    if 'custom_colors' not in st.session_state:
        from config import DEFAULT_COLORS
        st.session_state.custom_colors = DEFAULT_COLORS.copy()
    C = st.session_state.custom_colors
    
    current_user = st.session_state.get('username', 'المستثمر')

    with st.container():
        c_logo, c_nav, c_user = st.columns([1.5, 5.5, 1.5], gap="small")
        
        with c_logo:
            st.markdown(f"""
            <div style="display: flex; align-items: center; gap: 8px; padding-top: 5px;">
                <div class="app-logo-box">{APP_ICON}</div>
                <div><div class="logo-text">{APP_NAME}</div></div>
            </div>
            """, unsafe_allow_html=True)

        with c_nav:
            cols = st.columns(6, gap="small")
            nav_items = [("الرئيسة", "home"), ("مضاربة", "spec"), ("استثمار", "invest"), 
                         ("صكوك", "sukuk"), ("تحليل", "analysis"), ("سيولة", "cash")]
            for col, (label, key) in zip(cols, nav_items):
                is_active = (st.session_state.get('page') == key)
                with col:
                    if st.button(label, key=f"nav_{key}", type="primary" if is_active else "secondary", use_container_width=True):
                        st.session_state.page = key
                        st.rerun()

        with c_user:
            with st.popover(current_user, use_container_width=True):
                st.markdown(f"<div style='text-align:center; color:#9CA3AF; font-size:0.8rem; margin-bottom:10px;'>الملف الشخصي</div>", unsafe_allow_html=True)
                if st.button("⚙️  الإعدادات", key="u_set", use_container_width=True):
                    st.session_state.page = "settings"; st.rerun()
                if st.button("📥  إضافة عملية", key="u_add", use_container_width=True):
                    st.session_state.page = "add"; st.rerun()
                if st.button("🛠️  الأدوات", key="u_tools", use_container_width=True):
                    st.session_state.page = "tools"; st.rerun()
                st.markdown("---")
                if st.button("تسجيل الخروج", key="u_out", type="primary", use_container_width=True):
                    st.session_state.page = "logout"; st.rerun()
    st.markdown("---")

def render_kpi(label, value, color_condition=None, help_text=None):
    C = st.session_state.custom_colors
    val_c = C['main_text']
    if color_condition == "blue": val_c = C['primary']
    elif color_condition == "success": val_c = C['success']
    elif isinstance(color_condition, (int, float)): 
        val_c = C['success'] if color_condition >= 0 else C['danger']
    
    tooltip = f'title="{help_text}"' if help_text else ''
    st.markdown(f"""
    <div class="kpi-box" {tooltip}>
        <div style="color:{C['sub_text']}; font-size:0.8rem; font-weight:700; margin-bottom:5px;">{label}</div>
        <div class="kpi-value" style="color: {val_c} !important; direction:ltr;">{value}</div>
    </div>""", unsafe_allow_html=True)

def render_table(df, cols_def):
    if df.empty: st.info("لا توجد بيانات"); return
    headers = "".join([f"<th>{label}</th>" for _, label in cols_def])
    rows_html = ""
    
    for _, row in df.iterrows():
        cells = ""
        is_closed = str(row.get('status', '')).lower() in ['close', 'sold', 'مغلقة', 'مباعة']
        
        for k, _ in cols_def:
            val = row.get(k, "-")
            disp = val
            
            # --- معالجة التواريخ ---
            if 'date' in k and val: disp = str(val)[:10]
            
            # --- معالجة الحالة ---
            elif k == 'status':
                bg, fg, txt = ("#F3F4F6", "#4B5563", "مغلقة") if is_closed else ("#DCFCE7", "#166534", "مفتوحة")
                disp = f"<span style='background:{bg}; color:{fg}; padding:2px 10px; border-radius:12px; font-size:0.7rem; font-weight:800;'>{txt}</span>"
            
            # --- معالجة الأرقام والنسب والألوان ---
            elif isinstance(val, (int, float)) or (isinstance(val, str) and val.replace('.','',1).isdigit()):
                try:
                    num = float(val)
                    formatted_num = "{:,.2f}".format(num) # إجبار التقريب لمنزلتين
                    
                    # 1. تلوين الوزن الحالي مقارنة بالهدف (هامش 1%)
                    if k == 'current_weight':
                        target = float(row.get('target_percentage', 0))
                        diff = abs(num - target)
                        # أخضر إذا كان الفرق ضمن 1%، أحمر إذا تجاوز
                        color = "#10B981" if diff <= 1.0 else "#EF4444"
                        disp = f"<span style='color:{color}; font-weight:bold;'>{formatted_num}%</span>"
                    
                    # 2. تلوين المبلغ المتبقي (remaining)
                    elif k == 'remaining':
                        # موجب (شراء) أخضر، سالب (بيع) أحمر
                        color = "#10B981" if num >= 0 else "#EF4444"
                        disp = f"<span style='color:{color}; font-weight:bold; direction:ltr;'>{formatted_num}</span>"

                    # 3. الأرباح والخسائر والنسب
                    elif k in ['gain', 'gain_pct', 'net_profit', 'roi_pct', 'daily_change']:
                        if is_closed and k == 'daily_change': 
                            disp = "<span style='color:#9CA3AF'>-</span>"
                        else:
                            color = "#10B981" if num >= 0 else "#EF4444"
                            suffix = "%" if 'pct' in k or 'change' in k else ""
                            disp = f"<span style='color:{color}; direction:ltr; font-weight:bold;'>{formatted_num}{suffix}</span>"
                    
                    # 4. باقي الأرقام المالية (بدون تلوين)
                    elif k in ['market_value', 'total_cost', 'entry_price', 'current_price', 'target_percentage']:
                        suffix = "%" if 'percentage' in k else ""
                        disp = f"{formatted_num}{suffix}"
                    
                    else:
                        disp = formatted_num
                except: disp = val
            
            cells += f"<td>{disp}</td>"
        rows_html += f"<tr>{cells}</tr>"
        
    st.markdown(f"""<div style="overflow-x: auto;"><table class="finance-table"><thead><tr>{headers}</tr></thead><tbody>{rows_html}</tbody></table></div>""", unsafe_allow_html=True)
