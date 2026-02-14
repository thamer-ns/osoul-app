# app.py
import os
import sys
from typing import Optional

import streamlit as st

# -----------------------------------------------------------------------------
# 🔧 Import bootstrap
# بعض الرفعّات إلى GitHub تضع المشروع داخل مجلد فرعي (مثل: osoul-app-main).
# هذا البلوك يجعل imports يعمل حتى لو تغيّر مسار التشغيل.
# -----------------------------------------------------------------------------
_BASE_DIR = os.path.dirname(__file__)
_candidates = [
    _BASE_DIR,
    os.path.join(_BASE_DIR, "osoul-app-main"),
    os.path.join(_BASE_DIR, "osoul-app"),
]
for _p in _candidates:
    try:
        if _p and os.path.isdir(_p) and _p not in sys.path:
            sys.path.insert(0, _p)
    except Exception:
        pass

# الآن imports (بدون أوامر Streamlit قبل set_page_config)
from config import APP_NAME, APP_ICON

# ✅ يجب أن يكون هذا أول نداء Streamlit في الملف
from theme.global_ui import configure_page, apply_global_ui

configure_page(APP_NAME, APP_ICON)
apply_global_ui(rtl=True)

# باقي الـ imports بعد تهيئة الصفحة
from database import init_db
from styles import apply_custom_css

# ✅ (اختياري) إذا ضفت apply_ui_css داخل styles.py
try:
    from styles import apply_ui_css
except Exception:
    apply_ui_css = None

try:
    from components import inject_component_styles, render_app_header, inject_streamlit_ar_i18n
except Exception:
    inject_component_styles = None
    render_app_header = None
    inject_streamlit_ar_i18n = None


def _safe_image(path: str, width: Optional[int] = None):
    try:
        if path and os.path.exists(path):
            st.image(path, width=width)
    except Exception:
        pass


@st.cache_data(show_spinner=False)
def _init_db_once():
    """تهيئة DB مرة واحدة (خاصة في Streamlit Cloud)."""
    try:
        init_db()
        return True, ""
    except Exception as e:
        return False, str(e)


def main():
    # Arabic UI: translate Streamlit default placeholders
    # ✅ بعد set_page_config فقط (حتى لا يسبب مشاكل التهيئة)
    if inject_streamlit_ar_i18n:
        try:
            inject_streamlit_ar_i18n(True)
        except Exception:
            pass

    # CSS (آمن)
    try:
        apply_custom_css()
    except Exception:
        pass

    # CSS إضافي (اختياري)
    if apply_ui_css:
        try:
            apply_ui_css()
        except Exception:
            pass

    if inject_component_styles:
        try:
            inject_component_styles()
        except Exception:
            pass

    # Header (اختياري)
    if render_app_header:
        try:
            render_app_header("أصولي", "منصة الذكاء الكمي للأسواق")
        except Exception:
            pass

    # -------------------------
    # DB Init
    # -------------------------
    ok, err = _init_db_once()
    if not ok:
        st.error("❌ فشل تهيئة قاعدة البيانات. تأكد من DATABASE_URL في Secrets/Env.")
        if err:
            st.caption(err)

    # -------------------------
    # Auth Gate (من security.py)
    # -------------------------
    try:
        # ✅ توافق مع نسخ security المختلفة
        try:
            from security import login_system
        except Exception:
            from security import require_login as login_system
    except Exception as e:
        st.error("فشل تحميل نظام تسجيل الدخول (security.py).")
        st.code(str(e))
        st.stop()

    try:
        auth_ok = bool(login_system())
    except Exception as e:
        st.error("حدث خطأ أثناء نظام تسجيل الدخول.")
        st.code(str(e))
        st.stop()

    if not auth_ok:
        st.stop()

    # -------------------------
    # Router / Views
    # -------------------------
    try:
        from views import router
    except Exception as e:
        st.error("فشل تحميل واجهات التطبيق (views).")
        st.code(str(e))
        st.stop()

    try:
        router()
    except Exception as e:
        st.error("حدث خطأ غير متوقع في التطبيق.")
        st.code(str(e))
        st.stop()


if __name__ == "__main__":
    main()
