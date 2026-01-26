import streamlit as st
from config import APP_NAME, APP_ICON
from styles import apply_custom_css
from database import init_db
from security import login_system
from views import router

# 1. إعداد الصفحة (يجب أن يكون أول أمر)
st.set_page_config(
    page_title=APP_NAME,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2. تطبيق التصميم
apply_custom_css()

# 3. تهيئة قاعدة البيانات (إنشاء الجداول والترقية التلقائية)
init_db()

# 4. إدارة الحالة (Session State)
if 'page' not in st.session_state: st.session_state.page = 'home'

# 5. التوجيه (الدخول أو البرنامج)
if login_system():
    try:
        router()
    except Exception as e:
        st.error(f"حدث خطأ غير متوقع في العرض: {e}")
        # زر لإعادة التحميل في حال التعليق
        if st.button("إعادة تحميل البرنامج"):
            st.rerun()
