import streamlit as st
from config import DEFAULT_COLORS

def apply_custom_css():
    C = DEFAULT_COLORS
    if 'custom_colors' in st.session_state:
        C = st.session_state.custom_colors

    st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        /* === الأساسيات === */
        html, body, [class*="css"], .stMarkdown, h1, h2, h3, h4, p, label, div, span, th, td, button, input {{
            font-family: 'Cairo', sans-serif !important;
            direction: rtl; 
        }}
        .stApp {{ background-color: {C['page_bg']} !important; }}
        [data-testid="stHeader"] {{ background-color: rgba(255, 255, 255, 0.9) !important; backdrop-filter: blur(10px); }}
        [data-testid="stSidebar"] {{ display: none !important; }}

        /* === 1. جداول البيانات (تصميم الجوهرة) === */
        .finance-table-container {{
            overflow-x: auto;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.03);
            margin-bottom: 25px;
            border: 1px solid {C['border']};
            background-color: {C['card_bg']};
        }}
        .finance-table {{
            width: 100%; border-collapse: separate; border-spacing: 0;
            font-size: 0.95rem;
        }}
        .finance-table thead tr {{
            background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
        }}
        .finance-table th {{ 
            color: {C['primary']} !important; 
            padding: 18px 15px; 
            text-align: center; 
            border-bottom: 2px solid {C['border']}; 
            font-weight: 800; 
            white-space: nowrap;
        }}
        .finance-table td {{ 
            padding: 14px 15px; 
            text-align: center; 
            border-bottom: 1px solid {C['border']}; 
            color: {C['main_text']}; 
            font-weight: 600;
            transition: all 0.2s ease;
        }}
        .finance-table tbody tr:hover td {{ background-color: #f0f9ff; }}

        /* === 2. إصلاح الحقول السوداء === */
        input, .stTextInput input, .stNumberInput input, .stDateInput input, [data-baseweb="input"] {{
            background-color: #ffffff !important; 
            color: {C['main_text']} !important;
            border: 1px solid {C['border']} !important;
            border-radius: 10px !important;
            padding: 10px !important;
        }}
        
        /* === 3. بطاقات المؤشرات (KPIs) === */
        .kpi-box {{
            background-color: {C['card_bg']};
            border: 1px solid {C['border']};
            border-radius: 16px;
            padding: 20px;
            text-align: right;
            margin-bottom: 10px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
            transition: transform 0.2s;
        }}
        .kpi-box:hover {{ transform: translateY(-3px); }}
        .kpi-title {{ font-size: 0.9rem; color: {C['sub_text']}; font-weight: 700; margin-bottom: 8px; }}
        .kpi-value {{ font-size: 1.6rem; font-weight: 900; direction: ltr; }}
        
        /* === 4. صندوق تاسي === */
        .tasi-box {{
            background: linear-gradient(120deg, {C['primary']} 0%, #0f172a 100%) !important;
            padding: 30px; 
            border-radius: 20px; 
            margin-bottom: 30px; 
            display: flex; 
            justify-content: space-between; 
            align-items: center;
            box-shadow: 0 15px 30px -5px rgba(37, 99, 235, 0.3);
        }}
        .tasi-box * {{ color: #ffffff !important; }}
        
        /* === 5. الناف بار === */
        .navbar-box {{
            background-color: {C['card_bg']};
            padding: 15px 25px;
            border-bottom: 1px solid {C['border']};
            margin-bottom: 30px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        
        /* إخفاء العناوين الإنجليزية */
        div[data-testid="stSelectbox"] > label, div[data-testid="stTextInput"] > label,
        div[data-testid="stNumberInput"] > label, div[data-testid="stDateInput"] > label {{ display: none; }}
        
        /* أزرار Streamlit */
        div.stButton > button {{
            border-radius: 10px !important;
            font-weight: 700 !important;
            border: 1px solid {C['border']} !important;
            background-color: {C['card_bg']};
            color: {C['main_text']};
            box-shadow: 0 2px 5px rgba(0,0,0,0.02);
        }}
        div.stButton > button:hover {{
            border-color: {C['primary']} !important;
            color: {C['primary']} !important;
        }}
    </style>
    """, unsafe_allow_html=True)
