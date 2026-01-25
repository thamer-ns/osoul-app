import streamlit as st
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

# 3. CSS (التصميم الكامل - كايرو + تفاعل + RTL)
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
    
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
        border-radius: 12px !important; 
        border: 1px solid {C['border']} !important;
        padding: 10px !important;
        color: {C['main_text']} !important;
        font-family: 'Cairo' !important;
    }}
    
    /* === بطاقة تاسي (Gradient) === */
    .tasi-box {{
        background: linear-gradient(135deg, {C['primary']} 0%, #1e3a8a 100%);
        padding: 25px; 
        border-radius: 20px; 
        color: white !important;
        display: flex; 
        justify-content: space-between; 
        align-items: center;
        box-shadow: 0 10px 25px -5px rgba(37, 99, 235, 0.3); 
        margin-bottom: 30px;
        border: 1px solid rgba(255,255,255,0.1);
    }}
    
    /* === البطاقات الرقمية (KPI Box) === */
    .kpi-box {{
        background-color: {C['card_bg']}; 
        border: 1px solid {C['border']}; 
        border-radius: 16px;
        padding: 20px; 
        text-align: right; 
        margin-bottom: 15px; 
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); 
        transition: all 0.3s ease;
    }}
    .kpi-box:hover {{ 
        transform: translateY(-5px); 
        box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1);
    }}
    .kpi-value {{ 
        font-size: 1.8rem; 
        font-weight: 900; 
        direction: ltr; 
        display: inline-block; 
        margin-top: 5px;
        font-family: 'Cairo' !important;
    }}
    
    /* === الجداول (Finance Table) === */
    .finance-table-container {{
        background-color: {C['card_bg']};
        border-radius: 16px;
        border: 1px solid {C['border']};
        overflow: hidden;
        margin-bottom: 25px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.02);
    }}
    .finance-table {{ width: 100%; border-collapse: collapse; }}
    .finance-table th {{ 
        background-color: #F8FAFC; 
        padding: 15px; 
        text-align: right; 
        color: {C['sub_text']}; 
        font-size: 0.95rem; 
        font-weight: 800;
        border-bottom: 2px solid {C['border']};
    }}
    .finance-table td {{ 
        padding: 12px 15px; 
        text-align: right; 
        border-bottom: 1px solid {C['border']}; 
        font-size: 0.95rem; 
        vertical-align: middle;
        font-weight: 600;
        color: {C['main_text']};
    }}
    .finance-table tr:hover td {{ background-color: #F1F5F9; }}
    .finance-table tr:last-child td {{ border-bottom: none; }}
    
    /* === تصميم الناف بار === */
    .navbar-container {{
        background-color: {C['card_bg']};
        padding: 15px 25px;
        border-radius: 18px;
        border: 1px solid {C['border']};
        margin-bottom: 30px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 4px 20px rgba(0,0,0,0.04);
    }}
    
    /* إخفاء عناوين القوائم المنسدلة */
    div[data-testid="stSelectbox"] label {{
        display: none;
    }}
</style>
""", unsafe_allow_html=True)

# 4. تشغيل الموجه
views.router()
