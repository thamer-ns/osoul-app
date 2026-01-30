# app.py
import streamlit as st
from config import APP_NAME, APP_ICON
from security import login_system
from views import router
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

# DB Init (مرة واحدة)
if "db_initialized" not in st.session_state:
    st.session_state["db_initialized"] = False
if "db_init_lock" not in st.session_state:
    st.session_state["db_init_lock"] = False

if not st.session_state["db_initialized"] and not st.session_state["db_init_lock"]:
    st.session_state["db_init_lock"] = True
    try:
        init_db()
        st.session_state["db_initialized"] = True
    except Exception as e:
        st.session_state["db_initialized"] = False
        st.error("DB Error: فشل تهيئة قاعدة البيانات. تأكد من DATABASE_URL في secrets.")
        st.exception(e)
        st.stop()
    finally:
        st.session_state["db_init_lock"] = False

# ✅ حقن ستايلات components أولاً
if inject_component_styles:
    try:
        inject_component_styles()
    except Exception:
        pass

# ✅ ثم حقن styles.py أخيراً (عشان يغطي أي CSS ثاني)
apply_custom_css()

if "page" not in st.session_state:
    st.session_state["page"] = "home"

try:
    if login_system():
        router()
except Exception as e:
    st.error("حدث خطأ غير متوقع في التطبيق.")
    st.exception(e)
    st.stop()