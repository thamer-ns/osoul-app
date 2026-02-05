from osoli_logging import log_exception
# app.py
import os
import streamlit as st
from config import APP_NAME, APP_ICON
from database import init_db
from styles import apply_custom_css

# ✅ (اختياري) إذا ضفت apply_ui_css داخل styles.py
try:
    from styles import apply_ui_css
except ImportError as e:
    from osoli_logging import log_exception
    log_exception(e, "Optional import failed: styles.apply_ui_css", level="DEBUG")
    apply_ui_css = None

try:
    from components import inject_component_styles
except ImportError as e:
    from osoli_logging import log_exception
    log_exception(e, "Optional import failed: components.inject_component_styles", level="DEBUG")
    inject_component_styles = None

# ✅ (اختياري) هيدر احترافي (شعار + اسم + وصف + شريط حالة) بدون لمس منطق التحليل
try:
    from components import render_app_header
except ImportError as e:
    from osoli_logging import log_exception
    log_exception(e, "Optional import failed: components.render_app_header", level="DEBUG")
    render_app_header = None


from typing import Optional


def _safe_image(path: str, width: Optional[int] = None):
    """عرض صورة إن وجدت بدون كسر التطبيق."""
    try:
        if path and os.path.exists(path):
            st.image(path, width=width)
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
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
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
    return default_icon


def _get_selected_logo(path_default: str, session_key: str) -> str:
    """Return selected logo path if set and exists; otherwise fallback."""
    try:
        chosen = st.session_state.get(session_key)
        if chosen and os.path.exists(chosen):
            return chosen
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
    return path_default

st.set_page_config(
    page_title=APP_NAME,
    page_icon=_pick_page_icon(APP_ICON),
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ✅ إلغاء القائمة الجانبية نهائياً (حتى زر الفتح)
st.markdown(
    """
    <style>
      /* Hide Streamlit built-in sidebar + nav */
      section[data-testid="stSidebar"],
      div[data-testid="stSidebar"],
      nav[data-testid="stSidebarNav"],
      aside {
        display: none !important;
      }

      /* Hide the sidebar toggle / collapsed control (hamburger) */
      button[data-testid="collapsedControl"],
      div[data-testid="collapsedControl"],
      button[data-testid="stSidebarCollapsedControl"],
      div[data-testid="stSidebarCollapsedControl"] {
        display: none !important;
      }

      /* Hide Streamlit header toolbar / menu chrome */
      header,
      [data-testid="stHeader"],
      [data-testid="stToolbar"],
      #MainMenu,
      footer {
        visibility: hidden !important;
        height: 0px !important;
      }

      /* Remove top padding that Streamlit adds for header */
      .block-container {
        padding-top: 1rem !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
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
        # components.render_app_header expects (title=...) not (app_name=...)
        render_app_header(
            title=APP_NAME,
            subtitle="منصة التحليل الشامل: مالي + فني + كلاسيكي + مخاطر",
            logo_full_path=logo_full,
            logo_mark_path=logo_mark,
        )
    except Exception as e:
        log_exception(e, "render_app_header failed; falling back to simple image", level="WARNING")
        # fallback بسيط
        _safe_image(st.session_state.get("ui_logo_full") or "assets/logo_full.png", width=240)
else:
    _safe_image(st.session_state.get("ui_logo_full") or "assets/logo_full.png", width=240)

# ✅ السايدبار ملغي بالكامل

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
