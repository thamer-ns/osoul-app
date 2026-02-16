# app.py
import os
import sys

# Load local environment variables for development (safe no-op on Streamlit Cloud)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

import streamlit as st

# -----------------------------------------------------------------------------
# 🔧 Import bootstrap
# -----------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

PARENT_DIR = os.path.dirname(ROOT_DIR)
if PARENT_DIR and PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

# -----------------------------------------------------------------------------
# 🧩 App configuration
# -----------------------------------------------------------------------------
try:
    import config
    page_title = getattr(config, "APP_NAME", "أُصول")
    page_icon = getattr(config, "APP_ICON", "📈")
except Exception:
    page_title = "أُصول"
    page_icon = "📈"

st.set_page_config(
    page_title=page_title,
    page_icon=page_icon,
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# ✅ Global UI / RTL / Theme CSS (هذا هو اللي يرجّع الشكل كما كان)
# -----------------------------------------------------------------------------
try:
    from styles import apply_custom_css
except Exception:
    apply_custom_css = None

# Arabic UI: translate Streamlit default placeholders
try:
    from components import inject_streamlit_ar_i18n
except Exception:
    inject_streamlit_ar_i18n = None

# حقن الستايل مرة واحدة من البداية (مهم لتسجيل الدخول + RTL)
if "___css_applied" not in st.session_state:
    st.session_state["___css_applied"] = True
    try:
        if apply_custom_css:
            apply_custom_css()
    except Exception:
        pass
    try:
        if inject_streamlit_ar_i18n:
            inject_streamlit_ar_i18n(True)
    except Exception:
        pass

# -----------------------------------------------------------------------------
# ✅ Auth + Main Router (يرجع المحافظ + النافبار + التفاصيل)
# -----------------------------------------------------------------------------
from security import require_login  # noqa: E402
from views import router  # noqa: E402

if require_login():
    router()