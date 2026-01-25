import streamlit as st
from database import init_db
import views
from config import DEFAULT_COLORS, APP_NAME, APP_ICON

# 1. إعداد الصفحة
st.set_page_config(page_title=APP_NAME, layout="wide", page_icon=APP_ICON, initial_sidebar_state="collapsed")

# 2. تهيئة الألوان
if 'custom_colors' not in st.session_state:
    st.session_state.custom_colors = DEFAULT_COLORS.copy()
C = st.session_state.custom_colors

# 3. تهيئة قاعدة البيانات
if 'init' not in st.session_state:
    init_db()
    st.session_state['init'] = True
    st.session_state['page'] = 'home'

# 4. حقن التصميم (CSS Injection) - هذا ما يجعل البرنامج جميلاً
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
    
    /* تطبيق الخط على كل شيء */
    html, body, [class*="css"] {{
        font-family: 'Cairo', sans-serif;
    }}
    
    /* خلفية الصفحة */
    [data-testid="stAppViewContainer"] {{
        background-color: {C['page_bg']};
    }}
    
    /* الهيدر العلوي */
    [data-testid="stHeader"] {{
        background-color: rgba(255, 255, 255, 0.8);
        backdrop-filter: blur(10px);
        border-bottom: 1px solid {C['border']};
    }}

    /* === تصميم البطاقات (Cards) === */
    .kpi-box {{
        background-color: {C['card_bg']};
        border: 1px solid {C['border']};
        border-radius: 16px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        transition: transform 0.2s;
    }}
    .kpi-box:hover {{
        transform: translateY(-5px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
    }}
    .kpi-value {{
        font-size: 1.8rem;
        font-weight: 800;
        margin-top: 10px;
        direction: ltr;
    }}

    /* === صندوق تاسي (Gradient) === */
    .tasi-box {{
        background: linear-gradient(120deg, {C['primary']} 0%, #0f172a 100%);
        padding: 25px 35px;
        border-radius: 20px;
        color: white !important;
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 30px;
        box-shadow: 0 10px 25px -5px rgba(0, 82, 204, 0.3);
    }}
    .tasi-value {{
        font-size: 2.5rem;
        font-weight: 900;
        color: white;
        direction: ltr;
    }}

    /* === الجداول المخصصة === */
    .finance-table-container {{
        background-color: {C['card_bg']};
        border-radius: 16px;
        border: 1px solid {C['border']};
        overflow: hidden;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);
        margin-top: 15px;
    }}
    .finance-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.95rem;
    }}
    .finance-table th {{
        background-color: #FAFBFC;
        color: {C['sub_text']};
        font-weight: 700;
        padding: 16px;
        text-align: right;
        border-bottom: 2px solid {C['border']};
    }}
    .finance-table td {{
        padding: 14px 16px;
        border-bottom: 1px solid {C['border']};
        color: {C['main_text']};
        font-weight: 600;
    }}
    .finance-table tr:last-child td {{ border-bottom: none; }}
    .finance-table tr:hover {{ background-color: #F9FAFB; }}

    /* تحسين الأزرار */
    .stButton button {{
        border-radius: 10px;
        font-weight: 700;
        font-family: 'Cairo';
        border: none;
        transition: all 0.3s;
    }}
    
</style>
""", unsafe_allow_html=True)

# 5. تشغيل الموجه
views.router()
