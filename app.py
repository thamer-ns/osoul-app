# app.py
import os
import sys
from typing import Optional

import streamlit as st

# Arabic UI: translate Streamlit default placeholders
try:
    from components import inject_streamlit_ar_i18n
    inject_streamlit_ar_i18n(True)
except Exception:
    pass

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
from config import APP_NAME, APP_ICON, LOGO_MARK_PATH, REQUIRE_DB, DATABASE_URL
from database import init_db, db_healthcheck
from osoli_logging import redact_text, install_redaction_filter
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




# -----------------------------
# 🔧 DB Setup / Warning Page
# -----------------------------
def render_db_setup_page(err: str = "") -> None:
    """Show a single page when DB is required but not connected."""
    st.set_page_config(
        page_title=f"{APP_NAME} — إعداد قاعدة البيانات",
        page_icon=APP_ICON,
        layout="wide",
    )
    apply_custom_css()

    st.markdown(
        """
<div style="padding:14px 18px; border-radius:14px; background: linear-gradient(90deg, rgba(0,82,204,0.16), rgba(0,0,0,0.03));">
  <div style="text-align:right;">
    <div style="font-size:32px; font-weight:800;">تنبيه: قاعدة البيانات غير متصلة</div>
    <div style="opacity:.85; margin-top:6px;">التطبيق مُهيّأ للعمل على Postgres فقط. لن يتم تشغيل بقية النظام حتى يتم إصلاح الاتصال.</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    # Logo (optional)
    try:
        if LOGO_MARK_PATH and os.path.exists(LOGO_MARK_PATH):
            st.image(LOGO_MARK_PATH, width=80)
    except Exception:
        pass

    col1, col2 = st.columns([1.2, 1], gap="large")

    with col1:
        st.subheader("✅ ما المطلوب؟")
        st.markdown(
            """
- تأكد أن **DATABASE_URL** موجود في *Streamlit Cloud → App → Settings → Secrets*.
- تأكد أن رابط Postgres صحيح ويحتوي بيانات الدخول.
- (Supabase/Neon غالباً) أضف `?sslmode=require` إذا كان الخادم يتطلب SSL.
"""
        )
        st.code(
            """DATABASE_URL = "postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require"
TWELVEDATA_API_KEY = "YOUR_KEY"
AUTH_SECRET = "YOUR_LONG_RANDOM_SECRET""",
            language="toml",
        )
        st.caption("بعد تعديل Secrets: اضغط Rerun أو أعد تشغيل التطبيق من Streamlit Cloud.")

    with col2:
        st.subheader("🧪 فحص سريع")
        status = db_healthcheck()
        has_db_url = bool(status.get("has_db_url"))
        ok = bool(status.get("ok"))
        kind = status.get("kind") or "none"

        st.write({"has_db_url": has_db_url, "ok": ok, "kind": kind})

        if err:
            st.error(f"الخطأ: {redact_text(err)}")

        if not has_db_url and not DATABASE_URL:
            st.warning("لم يتم العثور على DATABASE_URL في Secrets/Env.")

        st.markdown(
            """**خطوات سريعة للإصلاح**
1) افتح Manage app → Settings → Secrets
2) أضف DATABASE_URL
3) احفظ
4) Restart/Reboot
"""
        )

    st.info("تم تعطيل SQLite fallback افتراضياً لمنع فقدان/تباعد البيانات.")

@st.cache_data(show_spinner=False)
def _init_db_once():
    """تهيئة DB مرة واحدة (خاصة في Streamlit Cloud)."""
    try:
        init_db()
        return True, ""
    except Exception as e:
        return False, redact_text(e)


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
            render_app_header()
        except Exception:
            pass

    # -------------------------
    # DB Init
    # -------------------------
    ok, err = _init_db_once()
    # ✅ مهم: لا نسمح باستمرار التطبيق على SQLite بالخطأ في الإنتاج
    try:
        from database import db_healthcheck
    except Exception:
        db_healthcheck = None

    if db_healthcheck is not None:
        hc = db_healthcheck()
        if getattr(config, "REQUIRE_DB", True) and (not hc.get("ok") or hc.get("kind") != "postgres"):
            # اعرض صفحة إعداد قاعدة البيانات وانهِ التنفيذ (بدون عرض أرقام 0.00 مضللة)
            render_db_setup_page(hc.get("error") or hc.get("pool_error") or err)
            st.stop()

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
