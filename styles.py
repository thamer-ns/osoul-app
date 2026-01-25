import streamlit as st
from config import DEFAULT_COLORS

def get_css():
    C = DEFAULT_COLORS
    return f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        /* تطبيق الخط على النصوص فقط واستثناء الأيقونات البرمجية */
        html, body, p, h1, h2, h3, h4, div, label, button, input, textarea, span, th, td {{
            font-family: 'Cairo', sans-serif !important;
            direction: rtl;
            color: {C['main_text']};
        }}
        
        /* استثناء الأيقونات المادية والرموز من الخط العربي لمنع التشوه */
        .material-icons, .st-emotion-cache-1pbowbk, .st-emotion-cache-1h9usn1, i {{
            font-family: 'Source Sans Pro', sans-serif !important;
            direction: ltr !important;
        }}

        .stApp {{ background-color: {C['page_bg']} !important; }}

        /* تحسين القائمة الجانبية */
        [data-testid="stSidebar"] {{
            background-color: {C['card_bg']} !important;
            border-left: 1px solid {C['border']};
        }}

        /* البطاقات الرقمية KPI */
        .kpi-box {{
            background-color: {C['card_bg']};
            border: 1px solid {C['border']};
            border-radius: 12px;
            padding: 15px;
            text-align: right;
            margin-bottom: 10px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.03);
        }}
        .kpi-label {{ font-size: 0.8rem; color: {C['sub_text']}; font-weight: 700; margin-bottom: 5px; }}
        .kpi-val {{ font-size: 1.3rem; font-weight: 800; direction: ltr; display: inline-block; }}

        /* الجداول المحسنة */
        .finance-table-container {{
            background-color: {C['card_bg']};
            border-radius: 8px;
            border: 1px solid {C['border']};
            overflow: hidden;
            margin-bottom: 20px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }}
        .finance-table {{ width: 100%; border-collapse: collapse; }}
        .finance-table th {{
            background-color: #FAFBFC; padding: 10px 15px; text-align: right;
            color: {C['sub_text']}; font-size: 0.85rem; font-weight: 700;
            border-bottom: 2px solid {C['border']}; white-space: nowrap;
        }}
        .finance-table td {{
            padding: 10px 15px; text-align: right;
            border-bottom: 1px solid {C['border']}; font-size: 0.9rem; font-weight: 600;
        }}
        .finance-table tr:hover td {{ background-color: #F8FAFC; }}
    </style>
    """

def apply_custom_css():
    st.markdown(get_css(), unsafe_allow_html=True)
