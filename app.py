"""Osoli Streamlit entry point."""
from __future__ import annotations

import logging
import os
import sys
import time
from typing import Tuple

import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    logging.getLogger(__name__).debug("Best-effort operation failed", exc_info=True)

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
    """Inject the visual theme, RTL shell, and final responsive density layer."""
    try:
        from styles import apply_custom_css
        from ui_polish import apply_ui_polish
        from ui_shell import apply_rtl_shell

        apply_custom_css()
        apply_rtl_shell()
        apply_ui_polish()
    except Exception:
        logger.exception("global stylesheet failed")


def _render_authenticated_header() -> None:
    try:
        from components import render_app_header

        render_app_header("أصولي", "منصة الذكاء الكمي وإدارة المحافظ")
    except Exception:
        logger.exception("header rendering failed")


def _install_runtime_hardening(username: str) -> None:
    from ai_engine_core.external_signal_journal_v5 import (
        install_external_signal_journal,
    )
    from ai_engine_core.reporting_policy_v5 import install_reporting_policy
    from ai_tenant_hardening import (
        install_ai_learning_scope,
        register_ai_tenant_tables,
    )
    from analysis_routes_v5 import install_analysis_routes
    from analytics_hardening import install_analytics_hardening
    from financial_data_router_v5 import install_financial_data_router
    from market_data_hardening import install_market_data_hardening
    from market_data_router_v5 import install_market_data_router
    from portfolio_metrics_v2 import install_portfolio_metrics_v2
    from tenant_scope import install_tenant_scope

    register_ai_tenant_tables()
    install_tenant_scope(username)
    install_market_data_hardening()
    install_market_data_router()
    install_financial_data_router()
    install_reporting_policy()
    install_external_signal_journal()
    install_ai_learning_scope()
    install_analytics_hardening()
    install_portfolio_metrics_v2()
    install_analysis_routes()


def _initialize_user_space(username: str) -> bool:
    for attempt in range(3):
        try:
            _install_runtime_hardening(username)
            st.session_state.pop("_tenant_init_failed", None)
            return True
        except Exception:
            logger.exception(
                "runtime hardening failed for authenticated user (attempt %s)",
                attempt + 1,
            )
            if attempt < 2:
                time.sleep(0.12 * (attempt + 1))
    st.session_state["_tenant_init_failed"] = True
    return False


def main() -> None:
    app_name, app_icon = _load_app_config()
    st.set_page_config(
        page_title=app_name,
        page_icon=app_icon if len(app_icon) <= 4 else "📈",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _apply_global_ui()

    ok, _ = _init_db_once()
    if not ok:
        st.error("تعذر الاتصال بقاعدة البيانات. راجع DATABASE_URL في Secrets.")
        st.stop()

    try:
        from database_security_hardening import install_database_security_hardening
        from database_write_hardening import install_database_write_hardening

        install_database_security_hardening()
        install_database_write_hardening()
    except Exception:
        logger.exception("database hardening failed")
        st.error("تعذر تهيئة حماية قاعدة البيانات.")
        st.stop()

    try:
        from persistent_auth_v5 import install_persistent_auth

        install_persistent_auth()
        from security import login_system

        authenticated = bool(login_system())
    except Exception:
        logger.exception("authentication failed")
        st.error("حدث خطأ في نظام الدخول.")
        st.stop()
    if not authenticated:
        st.stop()

    username = str(st.session_state.get("username") or "").strip()
    if not username or not _initialize_user_space(username):
        st.error("تعذر تهيئة مساحة بيانات المستخدم بأمان.")
        st.caption("تم منع فتح البيانات احترازيًا. أعد المحاولة بعد تحديث التطبيق.")
        if st.button("إعادة المحاولة", type="primary", use_container_width=True):
            st.session_state.pop("_tenant_init_failed", None)
            st.rerun()
        st.stop()

    _render_authenticated_header()

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
