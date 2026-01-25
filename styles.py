import streamlit as st
from config import DEFAULT_COLORS

def apply_custom_css():
    C = DEFAULT_COLORS
    if 'custom_colors' in st.session_state:
        C = st.session_state.custom_colors

    st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        /* === إعدادات الصفحة الأساسية === */
        html, body, [class*="css"], .stMarkdown, h1, h2, h3, h4, p, label, div, span, th, td, button, input {{
            font-family: 'Cairo', sans-serif !important;
            direction: rtl; 
        }}

        .stApp {{ background-color: {C['page_bg']} !important; }}
        [data-testid="stHeader"] {{ background-color: {C['page_bg']} !important; }}
        [data-testid="stSidebar"] {{ display: none !important; }}

        /* === إصلاح الحقول السوداء (مهم جداً) === */
        input, .stTextInput input, .stNumberInput input, .stDateInput input, [data-baseweb="input"] {{
            background-color: #ffffff !important; 
            color: {C['main_text']} !important;
            border: 1px solid {C['border']} !important;
            border-radius: 8px !important;
            padding: 10px !important;
        }}
        
        /* القوائم المنسدلة */
        div[data-baseweb="select"] > div {{
            background-color: #ffffff !important;
            color: {C['main_text']} !important;
            border: 1px solid {C['border']} !important;
            border-radius: 8px !important;
        }}
        div[data-baseweb="popover"], div[data-baseweb="menu"], ul[role="listbox"] {{
            background-color: #ffffff !important;
            border: 1px solid {C['border']} !important;
        }}
        li[role="option"] {{
            color: {C['main_text']} !important;
            background-color: #ffffff !important;
            text-align: right !important;
        }}

        /* === الجداول (تصميم الجوهرة) === */
        .finance-table-container {{
            overflow-x: auto;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.02);
            margin-bottom: 20px;
        }}
        .finance-table {{
            width: 100%; border-collapse: separate; border-spacing: 0;
            background-color: white; border: 1px solid {C['border']};
            border-radius: 12px; overflow: hidden;
            font-size: 0.95rem;
        }}
        .finance-table th {{ 
            background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
            color: {C['primary']} !important; 
            padding: 15px; 
            text-align: center; 
            border-bottom: 2px solid {C['border']}; 
            font-weight: 800; 
            white-space: nowrap;
        }}
        .finance-table td {{ 
            padding: 12px; 
            text-align: center; 
            border-bottom: 1px solid {C['border']}; 
            color: {C['main_text']}; 
            font-weight: 600;
            transition: background 0.2s;
        }}
        .finance-table tr:hover td {{ background-color: #f8fbff; }}

        /* === البطاقات (KPI & Ticker) === */
        .kpi-box {{
            background-color: white;
            border: 1px solid {C['border']};
            border-radius: 12px;
            padding: 15px;
            text-align: right;
            margin-bottom: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
            transition: transform 0.2s;
        }}
        .kpi-box:hover {{ transform: translateY(-2px); }}
        
        /* === صندوق تاسي === */
        .tasi-box {{
            background: linear-gradient(135deg, {C['primary']} 0%, #091E42 100%) !important;
            padding: 25px; 
            border-radius: 16px; 
            margin-bottom: 30px; 
            display: flex; 
            justify-content: space-between; 
            align-items: center;
            box-shadow: 0 10px 20px -5px rgba(0, 82, 204, 0.3);
        }}
        .tasi-box * {{ color: #ffffff !important; }}
        
        /* === الناف بار === */
        .navbar-box {{
            background-color: white;
            padding: 15px 20px;
            border-radius: 12px;
            border: 1px solid {C['border']};
            margin-bottom: 25px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.03);
        }}
        
        /* إخفاء العناوين الإنجليزية للحقول */
        div[data-testid="stSelectbox"] > label {{ display: none; }}
        div[data-testid="stTextInput"] > label {{ display: none; }}
        div[data-testid="stNumberInput"] > label {{ display: none; }}
        div[data-testid="stDateInput"] > label {{ display: none; }}
    </style>
    """, unsafe_allow_html=True)
