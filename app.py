# app.py
import streamlit as st
import os
from config import APP_NAME, APP_ICON
from database import init_db
from styles import apply_custom_css

# ✅ (اختياري) إذا ضفت apply_ui_css داخل styles.py
try:
    from styles import apply_ui_css
except Exception:
    apply_ui_css = None

try:
    from components import inject_component_styles
except Exception:
    inject_component_styles = None

# ----------------------------------------------
# Page config + App branding (assets/*)
# ----------------------------------------------
ASSETS_ICON = os.path.join("assets", "logo_mark.png")
ASSETS_FULL = os.path.join("assets", "logo_full.png")
ASSETS_APP  = os.path.join("assets", "logo_app.png")

_page_icon = APP_ICON
# Prefer brand mark if provided
try:
    if os.path.exists(ASSETS_ICON):
        _page_icon = ASSETS_ICON
except Exception:
    pass

st.set_page_config(
    page_title=APP_NAME,
    page_icon=_page_icon,
    layout="wide",
    initial_sidebar_state="collapsed",
)


st.markdown(
    "<style>#MainMenu{visibility:hidden;} footer{visibility:hidden;} header{visibility:hidden;}</style>",
    unsafe_allow_html=True
)

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

if inject_component_styles:
    try:
        inject_component_styles()
    except Exception as e:
        st.warning("تنبيه: حصل خطأ أثناء تحميل ستايلات components.")
        st.exception(e)

# ✅ CSS العام (لا تغيّره ولا تحطه تحت شرط)
apply_custom_css()

# ----------------------------------------------
# Brand header (safe if assets missing)
# ----------------------------------------------
try:
    if os.path.exists(ASSETS_ICON):
        st.sidebar.image(ASSETS_ICON, width=110)
except Exception:
    pass

# Top header inside main page (optional)
try:
    if os.path.exists(ASSETS_FULL):
        st.image(ASSETS_FULL, width=240)
except Exception:
    pass

# ✅ CSS واجهة النتائج (بطاقات/أيقونات) لو موجود
 (بطاقات/أيقونات) لو موجود
if apply_ui_css:
    apply_ui_css()

if "page" not in st.session_state:
    st.session_state["page"] = "home"

try:
    from security import login_system
    from views import router

    if login_system():
        router()
except Exception as e:
    st.error("حدث خطأ غير متوقع في التطبيق.")
    st.exception(e)
    st.stop()
