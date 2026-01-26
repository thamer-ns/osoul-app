import streamlit as st
import pandas as pd

def safe_fmt(val, suffix=""):
    try: return f"{float(val):,.2f}{suffix}"
    except: return "-"

def render_kpi(label, value, color_class="neutral", icon="📊"):
    # الألوان
    val_color = "#1E293B"
    if color_class == "success": val_color = "#059669"
    elif color_class == "danger": val_color = "#DC2626"
    elif color_class == "blue": val_color = "#2563EB"
    
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-icon-bg">{icon}</div>
        <div class="kpi-label">{label}</div>
        <div class="kpi-value" style="color: {val_color} !important;">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def render_ticker_card(symbol, name, price, change):
    col = "#059669" if change >= 0 else "#DC2626"
    bg = "#DCFCE7" if change >= 0 else "#FEE2E2"
    st.markdown(f"""
    <div class="kpi-card" style="padding: 15px; min-height: 120px;">
        <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
            <div style="font-weight:900; color:#1E293B;">{symbol}</div>
            <div style="direction:ltr; color:{col}; background:{bg}; padding:2px 8px; border-radius:8px; font-weight:800; font-size:0.8rem;">{change:+.2f}%</div>
        </div>
        <div style="font-size:1.5rem; font-weight:900; color:#0F172A;">{price:,.2f}</div>
        <div style="color:#94A3B8; font-size:0.75rem; font-weight:600;">{name}</div>
    </div>""", unsafe_allow_html=True)

def render_custom_table(df, columns_config):
    if df.empty: st.info("📭 لا توجد بيانات"); return
    html = '<div style="overflow-x:auto;"><table class="finance-table"><thead><tr>'
    for _, label, _ in columns_config: html += f'<th>{label}</th>'
    html += '</tr></thead><tbody>'
    for _, row in df.iterrows():
        html += '<tr>'
        for col_key, _, col_type in columns_config:
            val = row.get(col_key, "")
            display = val
            cls = ""
            if col_type == 'money':
                try: display = f"{float(val):,.2f}"
                except: pass
                cls = "txt-blue" if float(val if val else 0) > 0 else ""
            elif col_type == 'percent':
                try: v = float(val); display = f"{v:.2f}%"; cls = "txt-green" if v >= 0 else "txt-red"
                except: cls=""
            elif col_type == 'colorful':
                try: v = float(val); display = f"{v:,.2f}"; cls = "txt-green" if v >= 0 else "txt-red"
                except: cls=""
            elif col_type == 'badge':
                s = str(val).lower()
                is_op = s in ['open', 'مفتوحة']
                display = f'<span class="badge badge-{"open" if is_op else "closed"}">{"مفتوحة" if is_op else "مغلقة"}</span>'
            elif col_type == 'date': display = str(val)[:10]
            html += f'<td><span class="{cls}">{display}</span></td>'
        html += '</tr>'
    html += '</tbody></table></div>'
    st.markdown(html, unsafe_allow_html=True)
