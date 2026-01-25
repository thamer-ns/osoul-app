import streamlit as st
import pandas as pd
from database import init_db
import views
from config import DEFAULT_COLORS, APP_NAME, APP_ICON

# 1. إعداد الصفحة
st.set_page_config(
    page_title=APP_NAME, 
    layout="wide", 
    page_icon=APP_ICON, 
    initial_sidebar_state="collapsed"
)

# 2. تهيئة الألوان والقاعدة
if 'custom_colors' not in st.session_state:
    st.session_state.custom_colors = DEFAULT_COLORS.copy()
C = st.session_state.custom_colors

if 'init' not in st.session_state:
    init_db()
    st.session_state['init'] = True
    st.session_state['page'] = 'home'

# 3. CSS (التصميم المحسن - إصلاح الجداول والخطوط)
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;700;800&display=swap');
    
    /* === إعدادات الخط والاتجاه === */
    html, body, [class*="css"], p, h1, h2, h3, h4, div, label, button, input, textarea, span {{
        font-family: 'Cairo', sans-serif !important; 
        direction: rtl; 
        text-align: right;
    }}
    
    /* خلفية التطبيق */
    .stApp {{ background-color: {C['page_bg']} !important; }}
    
    /* إخفاء القائمة الجانبية */
    [data-testid="stSidebar"] {{ display: none; }}
    
    /* === تحسين الحقول والأزرار === */
    input, .stTextInput input, .stNumberInput input, .stSelectbox, .stDateInput input {{
        background-color: {C['input_bg']} !important; 
        border-radius: 10px !important; 
        border: 1px solid {C['border']} !important;
        padding: 8px !important;
        font-size: 0.9rem !important;
    }}
    
    /* === بطاقة تاسي (Gradient) === */
    .tasi-box {{
        background: linear-gradient(135deg, {C['primary']} 0%, #1e3a8a 100%);
        padding: 20px 25px; 
        border-radius: 18px; 
        color: white !important;
        display: flex; 
        justify-content: space-between; 
        align-items: center;
        box-shadow: 0 8px 20px -5px rgba(37, 99, 235, 0.3); 
        margin-bottom: 25px;
    }}
    
    /* === البطاقات الرقمية (KPI Box) === */
    .kpi-box {{
        background-color: {C['card_bg']}; 
        border: 1px solid {C['border']}; 
        border-radius: 14px;
        padding: 15px 20px; 
        text-align: right; 
        margin-bottom: 10px; 
        box-shadow: 0 2px 5px rgba(0,0,0,0.03); 
        transition: all 0.2s ease;
    }}
    .kpi-value {{ 
        font-size: 1.5rem; 
        font-weight: 800; 
        direction: ltr; 
        display: inline-block; 
        margin-top: 5px;
        font-family: 'Cairo' !important;
    }}
    
    /* === الجداول (الحل الجذري للأسطر) === */
    .finance-table-container {{
        background-color: {C['card_bg']};
        border-radius: 12px;
        border: 1px solid {C['border']};
        overflow-x: auto; /* سكرول أفقي عند الحاجة */
        margin-bottom: 25px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.02);
    }}
    .finance-table {{ width: 100%; border-collapse: collapse; min-width: 800px; }}
    
    .finance-table th {{ 
        background-color: #F8FAFC; 
        padding: 12px 10px; 
        text-align: right; 
        color: {C['sub_text']}; 
        font-size: 0.85rem; /* تصغير خط العناوين */
        font-weight: 700;
        border-bottom: 2px solid {C['border']};
        white-space: nowrap !important; /* منع نزول السطر */
    }}
    
    .finance-table td {{ 
        padding: 10px 10px; 
        text-align: right; 
        border-bottom: 1px solid {C['border']}; 
        font-size: 0.85rem; /* تصغير خط البيانات */
        font-weight: 600;
        color: {C['main_text']};
        white-space: nowrap !important; /* منع نزول السطر نهائياً */
        vertical-align: middle;
    }}
    
    .finance-table tr:hover td {{ background-color: #F8FAFC; }}
    .finance-table tr:last-child td {{ border-bottom: none; }}
    
    /* إخفاء عناوين القوائم المنسدلة */
    div[data-testid="stSelectbox"] label {{ display: none; }}
    div[data-testid="stTextInput"] label {{ display: none; }}
    div[data-testid="stNumberInput"] label {{ display: none; }}
    div[data-testid="stDateInput"] label {{ display: none; }}

</style>
""", unsafe_allow_html=True)

# 4. تشغيل الموجه
views.router()
