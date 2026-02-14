# app.py
import os
import sys
from typing import Optional

import streamlit as st

# Arabic UI: translate Streamlit default placeholders
from components import inject_streamlit_ar_i18n
# -----------------------------------------------------------------------------
# 🔧 Import bootstrap
# بعض الرفعّات إلى GitHub تضع المشروع داخل مجلد فرعي (مثل: osoul-app-main).
# هذا البلوك يجعل `import config` وباقي الوحدات يعمل حتى لو تغيّر مسار التشغيل.
# -----------------------------------------------------------------------------
_BASE_DIR = os.path.dirname(__file__)

# أضف المسار الحالي + أي مجلد فرعي يبدو أنه يحتوي ملفات المشروع
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

# الآن imports
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
    st.set_page_config(
        page_title=APP_NAME,
        page_icon=APP_ICON if isinstance(APP_ICON, str) and len(APP_ICON) <= 4 else "📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # CSS (آمن)
    try:
        apply_custom_css()
    except Exception:
        pass


    # DOM i18n (ترجمة نصوص Streamlit الافتراضية) - يجب أن يكون بعد set_page_config و CSS
    if not st.session_state.get("_os_i18n_done"):
        try:
            inject_streamlit_ar_i18n(True)
            st.session_state["_os_i18n_done"] = True
        except Exception:
            # Not fatal
            st.session_state["_os_i18n_done"] = True


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
        # ✅ تعديل بسيط فقط: توافق مع نسخ security المختلفة
        try:
            from security import login_system
        except Exception:
            from security import require_login as login_system
    except Exception as e:
        st.error("فشل تحميل نظام تسجيل الدخول (security.py).")
        st.code(str(e))
        st.stop()

    auth_ok = False
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
