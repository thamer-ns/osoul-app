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

# 3. محاولة تهيئة قاعدة البيانات (بدون إيقاف البرنامج إذا فشلت)
try:
    init_db()
except Exception as e:
    st.warning("⚠️ جاري محاولة الاتصال بقاعدة البيانات...")

# 4. إعدادات الجلسة الافتراضية (تجاوز تسجيل الدخول)
if 'page' not in st.session_state: st.session_state.page = 'home'
if 'username' not in st.session_state: st.session_state.username = "Admin" # اسم افتراضي
if 'logged_in' not in st.session_state: st.session_state.logged_in = True

# 5. تشغيل البرنامج مباشرة
try:
    router()
except Exception as e:
    # هذا الكود سيكشف لك السبب الحقيقي إذا لم تظهر البيانات
    st.error(f"حدث خطأ أثناء تحميل الواجهة: {e}")
    st.info("حاول ضغط زر Reboot App من قائمة Streamlit")
