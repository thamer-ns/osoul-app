"""Osoli Streamlit entry point."""
from __future__ import annotations

import logging
import os
import sys
from typing import Tuple

import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

logger = logging.getLogger("osoli.app")


def _load_app_config() -> Tuple[str, str]:
    try:
        from config import APP_ICON, APP_NAME

        return str(APP_NAME or "أصولي"), str(APP_ICON or "📈")
    except Exception:
        return "أصولي", "📈"


@st.cache_resource(show_spinner=False)
def _init_db_once() -> tuple[bool, str]:
    try:
        from database import init_db

        init_db()
        return True, ""
    except Exception as exc:
        logger.exception("database initialization failed")
        return False, str(exc)


def _apply_global_ui() -> None:
    helpers = []
    try:
        from styles import apply_custom_css, apply_ui_css

        helpers.extend([apply_custom_css, apply_ui_css])
    except Exception:
        pass
    try:
        from components import inject_component_styles, inject_streamlit_ar_i18n

        helpers.extend([lambda: inject_streamlit_ar_i18n(True), inject_component_styles])
    except Exception:
        pass
    for helper in helpers:
        try:
            helper()
        except Exception:
            logger.exception("optional UI helper failed")
    try:
        from components import render_app_header

        render_app_header("أصولي", "منصة الذكاء الكمي وإدارة المحافظ")
    except Exception:
        logger.exception("header rendering failed")


def _install_runtime_hardening(username: str) -> None:
    """Install compatibility fixes before any page modules are imported."""
    from analytics_hardening import install_analytics_hardening
    from market_data_hardening import install_market_data_hardening
    from tenant_scope import install_tenant_scope

    install_tenant_scope(username)
    install_market_data_hardening()
    install_analytics_hardening()


def main() -> None:
    app_name, app_icon = _load_app_config()
    st.set_page_config(
        page_title=app_name,
        page_icon=app_icon if len(app_icon) <= 4 else "📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _apply_global_ui()

    ok, _ = _init_db_once()
    if not ok:
        st.error("تعذر الاتصال بقاعدة البيانات. راجع DATABASE_URL في Secrets.")
        st.stop()

    try:
        from database_security_hardening import install_database_security_hardening

        install_database_security_hardening()
    except Exception:
        logger.exception("password hashing hardening failed")
        st.error("تعذر تهيئة حماية كلمات المرور.")
        st.stop()

    try:
        from security import login_system
    except Exception:
        logger.exception("security module import failed")
        st.error("تعذر تحميل نظام الدخول.")
        st.stop()

    try:
        authenticated = bool(login_system())
    except Exception:
        logger.exception("authentication failed")
        st.error("حدث خطأ في نظام الدخول.")
        st.stop()
    if not authenticated:
        st.stop()

    username = str(st.session_state.get("username") or "")
    try:
        _install_runtime_hardening(username)
    except Exception:
        logger.exception("runtime hardening failed")
        st.error("تعذر تهيئة مساحة بيانات المستخدم بأمان.")
        st.stop()

    if st.session_state.get("_tenant_unclaimed_legacy"):
        st.warning(
            "توجد بيانات قديمة غير مرتبطة بمستخدم، ولم تُنسب تلقائيًا لأن قاعدة البيانات تحتوي أكثر من حساب. "
            "راجع ترحيل البيانات قبل الاعتماد عليها."
        )

    try:
        from views import router

        router()
    except Exception:
        logger.exception("unhandled application error")
        st.error("حدث خطأ غير متوقع. تم تسجيل التفاصيل لدى الخادم.")
        st.stop()


if __name__ == "__main__":
    main()
