# app.py
import streamlit as st

from config import APP_NAME, APP_ICON
from styles import apply_custom_css
from security import login_system
from views import router
from database import init_db

# اختياري: ستايلات المكوّنات (KPI/جدول) بدون الاعتماد على ملف CSS خارجي
try:
    from components import inject_component_styles
except Exception:
    inject_component_styles = None


# ============================================================
# ✅ Streamlit Page Config (must be first Streamlit command)
# ============================================================
st.set_page_config(
    page_title=APP_NAME,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Hide Streamlit default UI
st.markdown(
    "<style>#MainMenu{visibility:hidden;} footer{visibility:hidden;} header{visibility:hidden;}</style>",
    unsafe_allow_html=True
)

# ============================================================
# ✅ DB Init (Fail-safe + avoid double init on reruns)
# ============================================================
# قفل بسيط لمنع تكرار init_db أثناء نفس الإقلاع
if "db_init_lock" not in st.session_state:
    st.session_state["db_init_lock"] = False

if "db_initialized" not in st.session_state and not st.session_state["db_init_lock"]:
    st.session_state["db_init_lock"] = True
    try:
        init_db()
        st.session_state["db_initialized"] = True
    except Exception as e:
        st.session_state["db_initialized"] = False
        st.error("DB Error: فشل تهيئة قاعدة البيانات. تأكد من إعداد DATABASE_URL في secrets.")
        # إذا تبي تخفي التفاصيل بالكامل: احذف السطرين الجايين
        st.exception(e)
        st.stop()
    finally:
        st.session_state["db_init_lock"] = False

# ============================================================
# ✅ CSS
# ============================================================
apply_custom_css()

# ستايلات المكوّنات (اختياري)
if inject_component_styles:
    try:
        inject_component_styles()
    except Exception:
        pass

# ============================================================
# ✅ Default Route State
# ============================================================
if "page" not in st.session_state:
    st.session_state["page"] = "home"

# ============================================================
# ✅ Auth + Router
# ============================================================
try:
    if login_system():
        router()
except Exception as e:
    st.error("حدث خطأ غير متوقع في التطبيق.")
    # إذا تبي تخفي التفاصيل احذف السطر التالي
    st.exception(e)
    st.stop()