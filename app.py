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
# بعض الرفعّات إلى GitHub تضع المشروع داخل مجلد فرعي (مثل: osoul-app-main).
# هذا البلوك يجعل الاستيرادات تعمل حتى لو تغيّر مسار التشغيل.
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

# Arabic UI: translate Streamlit default placeholders (called after set_page_config)
try:
    from components import inject_streamlit_ar_i18n
except Exception:
    inject_streamlit_ar_i18n = None

if inject_streamlit_ar_i18n:
    try:
        inject_streamlit_ar_i18n()
    except Exception:
        pass

# -----------------------------------------------------------------------------
# ✅ Auth + Main Router (This restores your original app structure)
# -----------------------------------------------------------------------------
from security import require_login  # noqa: E402
from views import router  # noqa: E402

# صفحة تسجيل الدخول (مع الشعار) موجودة داخل security.require_login()
if require_login():
    router()