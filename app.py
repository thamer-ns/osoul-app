# app.py
import os
import sys
from typing import Optional

# Load local environment variables for development (safe no-op on Streamlit Cloud)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

import streamlit as st

# Arabic UI: translate Streamlit default placeholders
# Arabic UI: translate Streamlit default placeholders (called after set_page_config)
try:
    from components import inject_streamlit_ar_i18n
except Exception:
    inject_streamlit_ar_i18n = None
# -----------------------------------------------------------------------------
# 🔧 Import bootstrap
# بعض الرفعّات إلى GitHub تضع المشروع داخل مجلد فرعي (مثل: osoul-app-main).
# هذا البلوك يجعل `import config` وباقي الوحدات يعمل حتى لو تغيّر مسار التشغيل.
# -----------------------
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# If running from a nested folder, also add parent to sys.path.
PARENT_DIR = os.path.dirname(ROOT_DIR)
if PARENT_DIR and PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# 🧩 App configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="أُصول",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

if inject_streamlit_ar_i18n:
    try:
        inject_streamlit_ar_i18n()
    except Exception:
        pass

# -----------------------------------------------------------------------------
# 🧭 Navigation
# -----------------------------------------------------------------------------
def _render_sidebar() -> str:
    st.sidebar.title("أُصول")
    st.sidebar.caption("منصة تحليل واستثمار")

    pages = {
        "الرئيسية": "home",
        "المستشار": "advisor",
        "الإشارات": "signals",
        "التقارير": "reports",
        "التحليل": "analysis",
        "الإعدادات": "settings",
    }

    choice = st.sidebar.radio("القائمة", list(pages.keys()), index=0)
    return pages[choice]


page = _render_sidebar()

# -----------------------------------------------------------------------------
# 🚀 Page router
# -----------------------------------------------------------------------------
def _safe_import_page(name: str):
    try:
        module = __import__(name, fromlist=["render"])
        return getattr(module, "render", None)
    except Exception as e:
        st.error(f"تعذر تحميل الصفحة: {name}")
        st.exception(e)
        return None


render_fn = None
if page == "home":
    render_fn = _safe_import_page("pages.home")
elif page == "advisor":
    render_fn = _safe_import_page("pages.advisor")
elif page == "signals":
    render_fn = _safe_import_page("pages.signals")
elif page == "reports":
    render_fn = _safe_import_page("pages.reports")
elif page == "analysis":
    render_fn = _safe_import_page("pages.analysis")
elif page == "settings":
    render_fn = _safe_import_page("pages.settings")

if render_fn:
    render_fn()
else:
    st.warning("الصفحة غير متاحة حالياً.")