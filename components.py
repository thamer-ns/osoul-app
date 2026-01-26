import streamlit as st

def safe_fmt(val, suffix=""):
    try: return f"{float(val):,.2f}{suffix}"
    except: return "-"

def render_kpi(label, value, color="blue", icon="💰"):
    # تحديد لون النص داخل المربع
    text_color_class = "txt-blue"
    if color == "success": text_color_class = "txt-green"
    elif color == "danger": text_color_class = "txt-red"
    
    # رسم المربع (HTML)
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-icon">{icon}</div>
        <div class="kpi-label">{label}</div>
        <div class="kpi-value {text_color_class}">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def render_ticker_card(symbol, name, price, change):
    col = "#10B981" if change >= 0 else "#EF4444"
    bg_icon = "📈" if change >= 0 else "📉"
    
    st.markdown(f"""
    <div class="kpi-card" style="padding: 15px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="font-weight:900; color:#0052CC; font-size:1.1rem;">{symbol}</div>
            <div style="direction:ltr; color:{col}; font-weight:800; background:{col}15; padding:2px 8px; border-radius:6px; font-size:0.85rem;">{change:+.2f}%</div>
        </div>
        <div style="font-size:1.4rem; font-weight:900; margin-top:5px; color:#1E293B;">{price:,.2f}</div>
        <div style="color:#94A3B8; font-size:0.75rem;">{name}</div>
    </div>
    """, unsafe_allow_html=True)

def render_custom_table(df, columns_config):
    if df.empty:
        st.info("📭 لا توجد بيانات متاحة")
        return

    html = '<div style="overflow-x:auto;"><table class="finance-table"><thead><tr>'
    for _, label, _ in columns_config: html += f'<th>{label}</th>'
    html += '</tr></thead><tbody>'
    
    for _, row in df.iterrows():
        html += '<tr>'
        for col_key, _, col_type in columns_config:
            val = row.get(col_key, "")
            display = val
            
            if col_type == 'money':
                try: display = f"{float(val):,.2f}"
                except: pass
                cls = "txt-blue" if float(val if val else 0) > 0 else ""
            elif col_type == 'percent':
                try: 
                    v = float(val); display = f"{v:.2f}%"
                    cls = "txt-green" if v >= 0 else "txt-red"
                except: cls=""
            elif col_type == 'colorful':
                try:
                    v = float(val); display = f"{v:,.2f}"
                    cls = "txt-green" if v >= 0 else "txt-red"
                except: cls=""
            elif col_type == 'badge':
                s = str(val).lower()
                is_op = s in ['open', 'مفتوحة']
                display = f'<span class="badge badge-{"open" if is_op else "closed"}">{"مفتوحة" if is_op else "مغلقة"}</span>'
                cls = ""
            elif col_type == 'date':
                display = str(val)[:10]
                cls = ""
            else: cls = ""
                
            html += f'<td><span class="{cls}">{display}</span></td>'
        html += '</tr>'
    html += '</tbody></table></div>'
    st.markdown(html, unsafe_allow_html=True)
