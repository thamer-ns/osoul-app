import streamlit as st
from config import APP_NAME, APP_ICON
from styles import apply_custom_css
from database import init_db
from views import router

# 1. إعداد الصفحة
st.set_page_config(
    page_title=APP_NAME,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2. تطبيق التصميم
apply_custom_css()

# 3. تهيئة قاعدة البيانات
try:
    init_db()
except:
    pass

# 4. إعداد الجلسة للدخول المباشر
if 'page' not in st.session_state: st.session_state.page = 'home'
if 'logged_in' not in st.session_state: st.session_state.logged_in = True
if 'username' not in st.session_state: st.session_state.username = "Admin"

# 5. تشغيل البرنامج
try:
    router()
except Exception as e:
    st.error("حدث خطأ أثناء تحميل الواجهة.")
    st.error(f"التفاصيل: {e}")
