import streamlit as st
from config import APP_NAME, APP_ICON, get_css
from security import login_system, logout
from views import router

# 1. إعداد الصفحة (يجب أن يكون أول سطر)
st.set_page_config(
    page_title=APP_NAME, 
    page_icon=APP_ICON, 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# 2. تطبيق التصميم الجديد (الألوان والخطوط)
st.markdown(get_css(), unsafe_allow_html=True)

# 3. تهيئة حالة الصفحة
if 'page' not in st.session_state:
    st.session_state.page = 'home'

# 4. نظام الدخول والتوجيه
if login_system():
    # إذا كان المستخدم مسجلاً للدخول
    if st.session_state.page == 'logout':
        logout()
    else:
        router()
