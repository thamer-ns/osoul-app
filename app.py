# app.pyimport os
import streamlit as st

from config import APP_NAME, APP_ICON
from database import init_db
from styles import apply_custom_css

# ✅ (اختياري) إذا ضفت apply_ui_css داخل styles.py
try:
    from styles import apply_ui_css
except Exception:
    apply_ui_css = None

# ✅ (اختياري) ستايلات components
try:
    from components import inject_component_styles
except Exception:
    inject_component_styles = None


def _safe_image(path: str, width: int | None = None):
    """عرض صورة إن وجدت بدون كسر التطبيق."""
    try:
        if path and os.path.exists(path):
            st.image(path, width=width)
    except Exception:
        pass


st.set_page_config(
    page_title=APP_NAME,
    page_icon="assets/logo_mark.png" if os.path.exists("assets/logo_mark.png") else APP_ICON,
    layout="wide",
    initial_sidebar_state="collapsed",
)

# إخفاء عناصر Streamlit الافتراضية
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

# ✅ حقن ستايلات المكوّنات إن كانت موجودة
if inject_component_styles:
    try:
        inject_component_styles()
    except Exception as e:
        st.warning("تنبيه: حصل خطأ أثناء تحميل ستايلات components.")
        st.exception(e)

# ✅ CSS العام (لا تغيّره ولا تحطه تحت شرط)
apply_custom_css()

# ✅ CSS واجهة النتائج (بطاقات/أيقونات) لو موجود
if apply_ui_css:
    try:
        apply_ui_css()
    except Exception:
        # لا نكسر التطبيق لو CSS اختياري فشل
        pass

# ✅ هيدر الشعار (اختياري/Fail-safe)
if os.path.exists("assets/logo_full.png"):
    _safe_image("assets/logo_full.png", width=240)

# ✅ سايدبار شعار صغير (اختياري/Fail-safe)
with st.sidebar:
    _safe_image("assets/logo_mark.png", width=120)

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
