import streamlit as st
import pandas as pd
import html

def safe_fmt(val, suffix=""):
    try:
        return f"{float(val):,.2f}{suffix}"
    except:
        return "-"

def render_kpi(label, value, color_class="neutral", icon="📊"):
    val_color = "#1E293B"
    if color_class == "success": val_color = "#059669"
    elif color_class == "danger": val_color = "#DC2626"
    elif color_class == "blue": val_color = "#2563EB"
    
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-icon-bg">{icon}</div>
        <div class="kpi-label">{label}</div>
        <div class="kpi-value" style="color:{val_color}!important;">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def render_ticker_card(symbol, name, price, change):
    col = "#059669" if change >= 0 else "#DC2626"
    bg = "#DCFCE7" if change >= 0 else "#FEE2E2"
    
    try: price_disp = f"{float(price):,.2f}"
    except: price_disp = "-"
    
    try: change_disp = f"{float(change):+.2f}%"
    except: change_disp = "0.00%"
    
    st.markdown(f"""
    <div class="kpi-card" style="padding:15px;min-height:120px;">
        <div style="display:flex;justify-content:space-between;margin-bottom:10px;">
            <div style="font-weight:900;color:#1E293B;">{symbol}</div>
            <div style="direction:ltr;color:{col};background:{bg};padding:2px 8px;border-radius:8px;font-weight:800;font-size:0.8rem;">
                {change_disp}
            </div>
        </div>
        <div style="font-size:1.5rem;font-weight:900;color:#0F172A;">{price_disp}</div>
        <div style="color:#94A3B8;font-size:0.75rem;font-weight:600;">{name}</div>
    </div>
    """, unsafe_allow_html=True)

def render_custom_table(df, columns_config):
    if df is None or df.empty:
        st.info("📭 لا توجد بيانات متاحة")
        return

    # بداية الجدول
    html_out = '<div style="overflow-x:auto;"><table class="finance-table"><thead><tr>'
    
    # الرؤوس
    for _, label, _ in columns_config:
        html_out += f'<th>{html.escape(str(label))}</th>'
    html_out += '</tr></thead><tbody>'
    
    # الصفوف
    for _, row in df.iterrows():
        html_out += '<tr>'
        for col_key, _, col_type in columns_config:
            val = row.get(col_key, "")
            display = str(val)
            cls = ""
            
            if col_type == 'money':
                try:
                    v = float(val)
                    display = f"{v:,.2f}"
                    cls = "txt-blue" if v > 0 else ""
                except:
                    display = "-"
            
            elif col_type == 'percent':
                try:
                    v = float(val)
                    display = f"{v:.2f}%"
                    cls = "txt-green" if v >= 0 else "txt-red"
                except:
                    display = "-"
            
            elif col_type == 'colorful':
                try:
                    v = float(val)
                    display = f"{v:,.2f}"
                    cls = "txt-green" if v >= 0 else "txt-red"
                except:
                    display = "-"
            
            elif col_type == 'badge':
                s = str(val).lower()
                is_op = s.startswith('open') or s.startswith('مفتوح')
                badge_cls = "badge-open" if is_op else "badge-closed"
                badge_text = "مفتوحة" if is_op else "مغلقة"
                display = f'<span class="badge {badge_cls}">{badge_text}</span>'
                html_out += f'<td>{display}</td>'
                continue 
            
            elif col_type == 'date':
                display = display[:10]
            
            # Sanitization Final Step
            if col_type != 'badge':
                display = html.escape(display)
                
            html_out += f'<td><span class="{cls}">{display}</span></td>'
        html_out += '</tr>'
        
    html_out += '</tbody></table></div>'
    st.markdown(html_out, unsafe_allow_html=True)
