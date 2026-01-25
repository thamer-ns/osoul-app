import streamlit as st
from config import APP_NAME, APP_ICON, get_css
from security import login_system, logout
from views import router
from database import init_db

# 1. إعداد الصفحة
st.set_page_config(
    page_title=APP_NAME, 
    page_icon=APP_ICON, 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# 2. تطبيق التصميم المفضل (CSS)
st.markdown(get_css(), unsafe_allow_html=True)

# 3. تهيئة الجداول عند التشغيل الأول
if 'init' not in st.session_state:
    init_db()
    st.session_state.init = True

# 4. تهيئة حالة الصفحة
if 'page' not in st.session_state:
    st.session_state.page = 'home'

# 5. نظام الدخول والتوجيه
if login_system():
    if st.session_state.page == 'logout':
        logout()
    else:
        router()
