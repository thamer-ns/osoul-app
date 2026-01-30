# app.py
import streamlit as st
from config import APP_NAME, APP_ICON
from styles import apply_custom_css
from security import login_system
from views import router
from database import init_db

# اختياري: ستايلات/تعريب المكوّنات
try:
    from components import inject_component_styles, inject_streamlit_ar_i18n
except Exception:
    inject_component_styles = None
    inject_streamlit_ar_i18n = None


# ============================================================
# ✅ Page Config (لازم يكون أول أوامر Streamlit)
# ============================================================
st.set_page_config(
    page_title=APP_NAME,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Hide Streamlit UI
st.markdown(
    "<style>#MainMenu{visibility:hidden;} footer{visibility:hidden;} header{visibility:hidden;}</style>",
    unsafe_allow_html=True
)

# ============================================================
# ✅ DB Init - مرة واحدة فقط (مع قفل ضد rerun)
# ============================================================
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
        # إذا تبي تخفي التفاصيل: احذف السطر التالي
        st.exception(e)
        st.stop()
    finally:
        st.session_state["db_init_lock"] = False

# ============================================================
# ✅ CSS
# ============================================================
apply_custom_css()

# (اختياري) ستايلات المكوّنات
if inject_component_styles:
    try:
        inject_component_styles()
    except Exception:
        pass

# ============================================================
# ✅ Fix: Streamlit placeholders English (Best-effort)
# ============================================================
# 1) تعريب DOM لعبارات Streamlit الافتراضية (Choose an option / Search / ...)
if inject_streamlit_ar_i18n:
    try:
        inject_streamlit_ar_i18n(True)
    except Exception:
        pass

# 2) CSS إضافي خفيف لتحسين RTL لبعض inputs (بدون كسر)
st.markdown(
    """
    <style>
      /* اجبار بعض مدخلات streamlit أن تكون RTL */
      [data-testid="stSelectbox"], [data-testid="stMultiSelect"], [data-testid="stTextInput"]{
        direction: rtl !important;
        text-align: right !important;
      }
      /* النصوص داخل select/multi غالبًا تكون LTR افتراضيًا */
      [data-testid="stSelectbox"] * , [data-testid="stMultiSelect"] *{
        direction: rtl !important;
      }
    </style>
    """,
    unsafe_allow_html=True
)

# ============================================================
# ✅ Default Page State
# ============================================================
if "page" not in st.session_state:
    st.session_state["page"] = "home"

# ============================================================
# ✅ Auth + Router (حماية من crash)
# ============================================================
try:
    if login_system():
        router()
except Exception as e:
    st.error("حدث خطأ غير متوقع في التطبيق.")
    # إذا تبي تخفي التفاصيل: احذف السطر التالي
    st.exception(e)
    st.stop()