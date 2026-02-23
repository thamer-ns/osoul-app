# app.py
from __future__ import annotations

import os
import sys
from typing import Optional, Tuple

import streamlit as st

# Load local environment variables for development (safe no-op on Streamlit Cloud)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    import logging
    logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at app.py:14')


# -----------------------------------------------------------------------------
# 🔧 Import bootstrap (supports running from root or nested folder in deployments)
# -----------------------------------------------------------------------------
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_BASE_DIR)

_candidates = [
    _BASE_DIR,
    _PARENT_DIR,
    os.path.join(_BASE_DIR, "osoul-app-main"),
    os.path.join(_BASE_DIR, "osoul-app"),
]
for _p in _candidates:
    try:
        if _p and os.path.isdir(_p) and _p not in sys.path:
            sys.path.insert(0, _p)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at app.py:34')


def _safe_image(path: str, width: Optional[int] = None) -> None:
    try:
        if path and os.path.exists(path):
            st.image(path, width=width)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at app.py:42')


def _load_app_config() -> Tuple[str, str]:
    """Load app title/icon without hard-failing if config is temporarily broken."""
    try:
        from config import APP_NAME, APP_ICON  # type: ignore
        name = str(APP_NAME or "أُصول")
        icon = str(APP_ICON or "📈")
        return name, icon
    except Exception:
        return "أُصول", "📈"


@st.cache_resource(show_spinner=False)
def _init_db_once() -> tuple[bool, str]:
    """تهيئة DB مرة واحدة (خاصة في Streamlit Cloud)."""
    try:
        from database import init_db  # import here to avoid early import side-effects
        init_db()
        return True, ""
    except Exception as e:
        return False, str(e)


def _apply_global_ui_once() -> None:
    """Apply CSS/i18n/component styles after set_page_config on EVERY rerun.

    مهم: CSS المحقون عبر st.markdown لا يستمر بين reruns، لذلك لا نستخدم
    session_state flag لمنع إعادة الحقن، وإلا ترجع الواجهة افتراضيًا (LTR).
    """

    # Optional imports: keep app working even if a cosmetic helper is missing.
    try:
        from styles import apply_custom_css  # type: ignore
    except Exception:
        apply_custom_css = None

    try:
        from styles import apply_ui_css  # type: ignore
    except Exception:
        apply_ui_css = None

    try:
        from components import inject_streamlit_ar_i18n  # type: ignore
    except Exception:
        inject_streamlit_ar_i18n = None

    try:
        from components import inject_component_styles  # type: ignore
    except Exception:
        inject_component_styles = None

    try:
        from components import render_app_header  # type: ignore
    except Exception:
        render_app_header = None

    # i18n should come after set_page_config so DOM is initialized.
    try:
        if inject_streamlit_ar_i18n:
            inject_streamlit_ar_i18n(True)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at app.py:105')

    try:
        if apply_custom_css:
            apply_custom_css()
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at app.py:111')

    try:
        if apply_ui_css:
            apply_ui_css()
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at app.py:117')

    try:
        if inject_component_styles:
            inject_component_styles()
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at app.py:123')

    try:
        if render_app_header:
            render_app_header("أصولي", "منصة الذكاء الكمي للأسواق")
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at app.py:129')


def main() -> None:
    app_name, app_icon = _load_app_config()

    # MUST be the first Streamlit command.
    st.set_page_config(
        page_title=app_name,
        page_icon=app_icon if isinstance(app_icon, str) and len(app_icon) <= 4 else "📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _apply_global_ui_once()  # apply CSS every rerun (Streamlit rebuilds DOM)

    # -------------------------
    # DB Init
    # -------------------------
    ok, err = _init_db_once()
    if not ok:
        st.error("❌ فشل تهيئة قاعدة البيانات. تأكد من DATABASE_URL في Secrets/Env.")
        if err:
            st.caption(err)

    # -------------------------
    # Auth Gate (supports multiple security.py variants)
    # -------------------------
    try:
        try:
            from security import login_system  # type: ignore
        except Exception:
            from security import require_login as login_system  # type: ignore
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
    # Router / Views (import after set_page_config + auth to reduce side effects)
    # -------------------------
    try:
        from views import router  # type: ignore
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
