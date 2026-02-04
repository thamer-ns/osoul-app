# app.py
import os
import streamlit as st
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

# ✅ (اختياري) هيدر احترافي (شعار + اسم + وصف + شريط حالة) بدون لمس منطق التحليل
try:
    from components import render_app_header
except Exception:
    render_app_header = None


from typing import Optional


def _safe_image(path: str, width: Optional[int] = None):
    """عرض صورة إن وجدت بدون كسر التطبيق."""
    try:
        if path and os.path.exists(path):
            st.image(path, width=width)
    except Exception:
        pass


def _pick_page_icon(default_icon):
    """اختيار أيقونة الصفحة مع fallback لو ما فيه assets."""
    try:
        # ✅ Prefer user selection (from Settings)
        chosen = st.session_state.get("ui_logo_mark")
        if chosen and os.path.exists(chosen):
            return chosen
        # ✅ Default asset
        if os.path.exists("assets/logo_mark.png"):
            return "assets/logo_mark.png"
    except Exception:
        pass
    return default_icon


def _get_selected_logo(path_default: str, session_key: str) -> str:
    """Return selected logo path if set and exists; otherwise fallback."""
    try:
        chosen = st.session_state.get(session_key)
        if chosen and os.path.exists(chosen):
            return chosen
    except Exception:
        pass
    return path_default

st.set_page_config(
    page_title=APP_NAME,
    page_icon=_pick_page_icon(APP_ICON),
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

# ✅ هيدر/شعار (Fail-safe)
if render_app_header:
    try:
        logo_full = st.session_state.get("ui_logo_full") or "assets/logo_full.png"
        logo_mark = st.session_state.get("ui_logo_mark") or "assets/logo_mark.png"
        render_app_header(
            app_name=APP_NAME,
            subtitle="منصة التحليل الشامل: مالي + فني + كلاسيكي + مخاطر",
            logo_full_path=logo_full,
            logo_mark_path=logo_mark,
        )
    except Exception:
        # fallback بسيط
        _safe_image(st.session_state.get("ui_logo_full") or "assets/logo_full.png", width=240)
else:
    _safe_image(st.session_state.get("ui_logo_full") or "assets/logo_full.png", width=240)

with st.sidebar:
    _safe_image(st.session_state.get("ui_logo_mark") or "assets/logo_mark.png", width=120)

# ✅ CSS واجهة النتائج (بطاقات/أيقونات) لو موجود
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
