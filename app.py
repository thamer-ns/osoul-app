# app.py
from __future__ import annotations

import logging
import os
import sys
import uuid
from typing import Tuple

import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

logger = logging.getLogger(__name__)


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
        logger.exception("Database initialization failed")
        return False, str(exc)


def _apply_global_ui() -> None:
    for module_name, function_name, args in (
        ("components", "inject_streamlit_ar_i18n", (True,)),
        ("styles", "apply_custom_css", ()),
        ("styles", "apply_ui_css", ()),
        ("components", "inject_component_styles", ()),
        ("components", "render_app_header", ("أصولي", "منصة عربية لإدارة المحافظ والتحليل وإدارة المخاطر")),
    ):
        try:
            module = __import__(module_name, fromlist=[function_name])
            function = getattr(module, function_name, None)
            if callable(function):
                function(*args)
        except Exception:
            logger.exception("Optional UI helper failed: %s.%s", module_name, function_name)


def _safe_error(message: str, exc: Exception | None = None) -> None:
    error_id = uuid.uuid4().hex[:10]
    st.error(f"{message} — رقم الخطأ: {error_id}")
    if exc is not None:
        logger.exception("%s [%s]", message, error_id, exc_info=exc)


def main() -> None:
    app_name, app_icon = _load_app_config()
    st.set_page_config(
        page_title=app_name,
        page_icon=app_icon if isinstance(app_icon, str) and len(app_icon) <= 4 else "📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _apply_global_ui()

    ok, _ = _init_db_once()
    if not ok:
        st.error("تعذر تهيئة قاعدة البيانات. تحقق من DATABASE_URL في إعدادات النشر.")
        st.stop()

    try:
        from security_v2 import require_login

        authenticated = bool(require_login())
    except Exception as exc:
        _safe_error("تعذر تحميل نظام الدخول الآمن", exc)
        st.stop()
    if not authenticated:
        st.stop()

    try:
        from tenant_db import ensure_tenant_schema
        from tenant_runtime import install_runtime_guards

        if not ensure_tenant_schema() or not install_runtime_guards():
            st.warning("تعذر إكمال ترقية عزل بيانات المستخدمين. أوقف إدخال البيانات حتى مراجعة السجل.")
            st.stop()
    except Exception as exc:
        _safe_error("تعذر تهيئة عزل بيانات المستخدمين", exc)
        st.stop()

    try:
        from views import router

        router()
    except Exception as exc:
        _safe_error("حدث خطأ غير متوقع في التطبيق", exc)
        st.stop()


if __name__ == "__main__":
    main()
