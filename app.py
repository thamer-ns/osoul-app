import streamlit as st
from config import APP_NAME, APP_ICON
from styles import apply_custom_css
from security import login_system
from views import router
from database import init_db

# 1. إعداد الصفحة (يجب أن يكون أول أمر Streamlit)
st.set_page_config(
    page_title=APP_NAME,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2. تهيئة قاعدة البيانات
if 'db_initialized' not in st.session_state:
    init_db()
    st.session_state['db_initialized'] = True

# 3. تطبيق التصميم
apply_custom_css()

# 4. إدارة الحالة والجلسة
if 'page' not in st.session_state: 
    st.session_state.page = 'home'

# 5. نظام الدخول والتوجيه
if login_system():
    router()
