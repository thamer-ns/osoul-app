import streamlit as st
import pandas as pd

def safe_fmt(val, suffix=""):
    try:
        x = float(val)
        return f"{x:,.2f}{suffix}"
    except: return "-"

def render_kpi(label, value, color_class="neutral"):
    color = "#374151"
    if color_class == "success": color = "#059669"
    elif color_class == "danger": color = "#DC2626"
    elif color_class == "blue": color = "#2563EB"
    
    st.markdown(f"""
    <div class="summary-card">
        <div style="color:#6B7280; font-size:0.9rem; margin-bottom:5px;">{label}</div>
        <div style="color:{color}; font-size:1.6rem; font-weight:800; direction:ltr;">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def render_ticker_card(symbol, name, price, change):
    col = "#059669" if change >= 0 else "#DC2626"
    st.markdown(f"""
    <div style="background:white; padding:12px; border-radius:10px; border:1px solid #eee; margin-bottom:10px;">
        <div style="display:flex; justify-content:space-between;">
            <span style="font-weight:bold; color:#1F2937;">{symbol}</span>
            <span style="color:{col}; direction:ltr; font-weight:bold;">{change:+.2f}%</span>
        </div>
        <div style="font-size:1.4rem; font-weight:900; color:#111827; margin-top:5px;">{price:,.2f}</div>
        <div style="color:#6B7280; font-size:0.8rem;">{name}</div>
    </div>
    """, unsafe_allow_html=True)

def render_custom_table(df, columns_config):
    """
    رسم جدول HTML مخصص مطابق للتصميم في الصور
    columns_config: قائمة من (اسم_العمود_في_الداتا, العنوان_للعرض, نوع_التنسيق)
    types: 'text', 'money', 'percent', 'badge', 'colorful'
    """
    if df.empty:
        st.info("لا توجد بيانات للعرض")
        return

    # بداية الجدول
    html = '<div style="overflow-x:auto;"><table class="finance-table">'
    
    # الرأس
    html += '<thead><tr>'
    for _, label, _ in columns_config:
        html += f'<th>{label}</th>'
    html += '</tr></thead><tbody>'
    
    # الصفوف
    for _, row in df.iterrows():
        html += 'tr'
        for col_key, _, col_type in columns_config:
            val = row.get(col_key, "")
            display_val = val
            
            # معالجة التنسيق
            cell_class = ""
            
            if col_type == 'money':
                try: display_val = f"{float(val):,.2f}"
                except: pass
                cell_class = "val-neu"
                
            elif col_type == 'percent':
                try: 
                    v = float(val)
                    display_val = f"{v:.2f}%"
                    # تلوين النسبة
                    if 'gain' in col_key or 'change' in col_key:
                        cell_class = "val-pos" if v >= 0 else "val-neg"
                    else:
                        cell_class = "val-blue" # للأوزان مثلاً
                except: pass
                
            elif col_type == 'colorful': # للأرباح والقيم المالية الملونة
                try:
                    v = float(val)
                    display_val = f"{v:,.2f}"
                    cell_class = "val-pos" if v >= 0 else "val-neg"
                except: pass
                
            elif col_type == 'badge':
                status = str(val).lower()
                if status in ['open', 'مفتوحة']:
                    display_val = '<span class="badge-open">مفتوحة</span>'
                else:
                    display_val = '<span class="badge-closed">مغلقة</span>'
            
            elif col_type == 'date':
                display_val = str(val)[:10]
                
            html += f'<td><div class="{cell_class}">{display_val}</div></td>'
        html += '</tr>'
        
    html += '</tbody></table></div>'
    st.markdown(html, unsafe_allow_html=True)
