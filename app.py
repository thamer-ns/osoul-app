import streamlit as st
from config import APP_NAME, APP_ICON
from database import init_db
from styles import apply_custom_css

try:
    from components import inject_component_styles
except Exception:
    inject_component_styles = None

st.set_page_config(
    page_title=APP_NAME,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    "<style>#MainMenu{visibility:hidden;} footer{visibility:hidden;} header{visibility:hidden;}</style>",
    unsafe_allow_html=True
)

# ✅ DB Init (مرة واحدة لكل سيرفر) — أقوى من session_state lock
@st.cache_resource
def _init_db_once():
    init_db()
    return True

try:
    _init_db_once()
except Exception as e:
    st.error("DB Error: فشل تهيئة قاعدة البيانات. تأكد من DATABASE_URL في secrets.")
    st.exception(e)
    st.stop()

# ✅ حقن ستايلات components أولاً
if inject_component_styles:
    try:
        inject_component_styles()
    except Exception as e:
        # لا نوقف التطبيق، لكن لا نخفي الخطأ بالكامل
        st.warning("تنبيه: حصل خطأ أثناء تحميل ستايلات components.")
        st.exception(e)

# ✅ ثم حقن styles.py أخيراً (عشان يغطي أي CSS ثاني)
apply_custom_css()

if "page" not in st.session_state:
    st.session_state["page"] = "home"

try:
    # (اختياري) Lazy import لتقليل أخطاء الاستيراد المبكر
    from security import login_system
    from views import router

    if login_system():
        router()
except Exception as e:
    st.error("حدث خطأ غير متوقع في التطبيق.")
    st.exception(e)
    st.stop()