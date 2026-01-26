import streamlit as st
from config import APP_NAME, APP_ICON
from styles import apply_custom_css
from security import login_system
from views import router

# إعداد الصفحة
st.set_page_config(page_title=APP_NAME, page_icon=APP_ICON, layout="wide", initial_sidebar_state="collapsed")

# التصميم
apply_custom_css()

# إدارة الجلسة
if 'page' not in st.session_state: st.session_state.page = 'home'

# التشغيل
if login_system():
    router()
