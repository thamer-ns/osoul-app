import streamlit as st
import pandas as pd
from database import init_db
import views
from config import DEFAULT_COLORS, APP_NAME, APP_ICON

# 1. إعداد الصفحة (يجب أن يكون أول سطر)
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

# 3. حقن التصميم (CSS) - النسخة المدمجة والجميلة
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
    
    /* === إجبار الاتجاه من اليمين لليسار === */
    html, body, [class*="css"], .stMarkdown, .stButton, .stSelectbox, .stNumberInput {{
        font-family: 'Cairo', sans-serif !important;
        direction: rtl !important;
        text-align: right !important;
    }}
    
    /* خلفية الصفحة */
    .stApp {{
        background-color: {C['page_bg']} !important;
    }}
    
    /* إخفاء القائمة الجانبية وزر التطوير */
    [data-testid="stSidebar"] {{ display: none; }}
    footer {{ visibility: hidden; }}
    #MainMenu {{ visibility: hidden; }}

    /* === تصميم البطاقات (KPI Cards) === */
    .kpi-card {{
        background-color: {C['card_bg']};
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.05);
        border: 1px solid {C['border']};
        text-align: right;
        transition: transform 0.3s ease;
        margin-bottom: 15px;
    }}
    .kpi-card:hover {{
        transform: translateY(-5px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.1);
    }}
    .kpi-label {{
        color: {C['sub_text']};
        font-size: 0.9rem;
        font-weight: 700;
        margin-bottom: 8px;
    }}
    .kpi-value {{
        color: {C['primary']};
        font-size: 1.8rem;
        font-weight: 900;
        font-family: 'Cairo';
    }}

    /* === صندوق تاسي (التصميم الجميل) === */
    .tasi-container {{
        background: linear-gradient(135deg, {C['primary']} 0%, #091E42 100%);
        color: white !important;
        padding: 25px 30px;
        border-radius: 20px;
        box-shadow: 0 10px 30px rgba(0, 82, 204, 0.25);
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 30px;
    }}
    
    /* === الجداول (Finance Table) === */
    .finance-table {{
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        background-color: {C['card_bg']};
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid {C['border']};
        margin-top: 10px;
    }}
    .finance-table th {{
        background-color: #FAFBFC;
        color: {C['sub_text']};
        font-weight: 800;
        padding: 15px;
        text-align: right;
        border-bottom: 2px solid {C['border']};
    }}
    .finance-table td {{
        padding: 12px 15px;
        border-bottom: 1px solid {C['border']};
        color: {C['main_text']};
        font-weight: 600;
        text-align: right;
    }}
    .finance-table tr:hover td {{
        background-color: #F4F5F7;
    }}

    /* === الناف بار (القائمة العلوية) === */
    .nav-container {{
        background-color: {C['card_bg']};
        padding: 15px 20px;
        border-radius: 16px;
        border: 1px solid {C['border']};
        box-shadow: 0 4px 15px rgba(0,0,0,0.03);
        margin-bottom: 25px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }}
    
    /* تحسين الأزرار */
    div.stButton > button {{
        width: 100%;
        border-radius: 10px;
        font-weight: 700;
        padding: 0.5rem;
        transition: all 0.3s;
    }}
</style>
""", unsafe_allow_html=True)

# 4. تشغيل التطبيق
views.router()
