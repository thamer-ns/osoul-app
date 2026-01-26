import streamlit as st
from config import APP_NAME, APP_ICON
from styles import apply_custom_css
from database import init_db
from security import login_system, logout
from views import router

# 1. إعداد الصفحة
st.set_page_config(
    page_title=APP_NAME,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2. تطبيق التصميم وقاعدة البيانات
apply_custom_css()
init_db()

# 3. نظام التوجيه
if 'page' not in st.session_state: st.session_state.page = 'home'

if login_system():
    try:
        router()
        # زر خروج صغير في القائمة الجانبية (اختياري)
        with st.sidebar:
            if st.button("تسجيل خروج"):
                logout()
    except Exception as e:
        st.error(f"حدث خطأ غير متوقع: {e}")
