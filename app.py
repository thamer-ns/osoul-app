# app.py
import streamlit as st
from config import APP_NAME, APP_ICON
from database import init_db
from styles import apply_custom_css

# ✅ Optional UI CSS
try:
    from styles import apply_ui_css
except Exception:
    apply_ui_css = None

# ✅ Optional component styles
try:
    from components import inject_component_styles
except Exception:
    inject_component_styles = None

# ------------------------------------------------------------
# Streamlit page config (must be early)
# ------------------------------------------------------------
try:
    st.set_page_config(
        page_title=APP_NAME,
        page_icon=APP_ICON,
        layout="wide",
        initial_sidebar_state="collapsed",
    )
except Exception as e:
    st.error("Streamlit config error: تعذر تهيئة إعدادات الصفحة.")
    st.exception(e)
    st.stop()

# Hide Streamlit UI chrome
st.markdown(
    "<style>#MainMenu{visibility:hidden;} footer{visibility:hidden;} header{visibility:hidden;}</style>",
    unsafe_allow_html=True
)

# ------------------------------------------------------------
# DB init - once per session/process
# ------------------------------------------------------------
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

# ------------------------------------------------------------
# Styles (avoid heavy re-injection)
# ------------------------------------------------------------
if "css_loaded" not in st.session_state:
    st.session_state["css_loaded"] = True

    # small UI component styles
    if inject_component_styles:
        try:
            inject_component_styles()
        except Exception as e:
            st.warning("تنبيه: حصل خطأ أثناء تحميل ستايلات components.")
            st.exception(e)

    # global css
    try:
        apply_custom_css()
    except Exception as e:
        st.warning("تنبيه: حصل خطأ أثناء تحميل CSS العام.")
        st.exception(e)

    # result UI css if exists
    if apply_ui_css:
        try:
            apply_ui_css()
        except Exception as e:
            st.warning("تنبيه: حصل خطأ أثناء تحميل CSS واجهة النتائج.")
            st.exception(e)

# ------------------------------------------------------------
# Default routing state
# ------------------------------------------------------------
st.session_state.setdefault("page", "home")

# ------------------------------------------------------------
# Auth + router
# ------------------------------------------------------------
try:
    from security import login_system
except Exception as e:
    st.error("Auth Error: تعذر تحميل نظام تسجيل الدخول (security.py).")
    st.exception(e)
    st.stop()

try:
    from views import router
except Exception as e:
    st.error("Router Error: تعذر تحميل الموجه (views/router).")
    st.exception(e)
    st.stop()

try:
    if login_system():
        router()
except Exception as e:
    st.error("حدث خطأ غير متوقع أثناء تشغيل التطبيق.")
    st.exception(e)
    st.stop()
