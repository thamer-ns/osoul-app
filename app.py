import streamlit as st
from config import APP_NAME, APP_ICON
from styles import apply_custom_css
from database import init_db
from security import login_system, logout
from views import router

# 1. إعداد الصفحة (أول سطر إلزامي)
st.set_page_config(
    page_title=APP_NAME,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2. تطبيق التصميم
apply_custom_css()

# 3. تهيئة قاعدة البيانات (لضمان وجود جدول المستخدمين)
try:
    init_db()
except Exception as e:
    print(f"DB Init Warning: {e}")

# 4. نظام التوجيه وإدارة الجلسة
if 'page' not in st.session_state: st.session_state.page = 'home'

# 5. تشغيل نظام الحماية
# إذا نجح الدخول، يتم عرض البرنامج
if login_system():
    try:
        # عرض البرنامج الرئيسي
        router()
        
        # زر تسجيل الخروج في القائمة الجانبية
        with st.sidebar:
            st.markdown("---")
            if st.button("🚪 تسجيل خروج", use_container_width=True):
                logout()
                
    except Exception as e:
        st.error("حدث خطأ غير متوقع في الواجهة.")
        st.error(f"التفاصيل: {e}")
        if st.button("إعادة تشغيل"):
            st.rerun()
