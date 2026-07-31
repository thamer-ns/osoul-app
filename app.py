"""Osoli Streamlit entry point."""
from __future__ import annotations

import importlib
import logging
import os
import sys
import time
from collections.abc import Callable
from typing import Any, Tuple

import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    logging.getLogger(__name__).debug(
        "Best-effort operation failed",
        exc_info=True,
    )

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
def _init_db_once() -> bool:
    """Initialize once after success; exceptions are intentionally not cached."""
    from database_pool_hardening_v6 import install_threadsafe_database_pool

    # Must run before init_db obtains the first process-global connection.
    install_threadsafe_database_pool()
    from database import init_db

    init_db()
    return True


def _initialize_database() -> tuple[bool, str]:
    try:
        return bool(_init_db_once()), ""
    except Exception as exc:
        logger.exception("database initialization failed")
        return False, str(exc)


def _apply_global_ui() -> None:
    """Inject the visual theme, RTL shell, and responsive density layer."""
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

        render_app_header(
            "أصولي",
            "منصة الذكاء الكمي وإدارة المحافظ",
        )
    except Exception:
        logger.exception("header rendering failed")


def _invoke_runtime(module_name: str, function_name: str, *args: Any) -> Any:
    module = importlib.import_module(module_name)
    function = getattr(module, function_name)
    return function(*args)


def _runtime_failures() -> list[str]:
    raw = st.session_state.get("_runtime_optional_failures") or []
    return [str(item) for item in raw if str(item).strip()]


def _set_optional_failure(stage: str, failed: bool) -> None:
    failures = _runtime_failures()
    if failed and stage not in failures:
        failures.append(stage)
    if not failed:
        failures = [item for item in failures if item != stage]
    st.session_state["_runtime_optional_failures"] = failures


def _run_runtime_stage(
    stage: str,
    operation: Callable[[], Any],
    *,
    critical: bool,
) -> bool:
    """Run one bootstrap stage and isolate non-security feature failures."""
    try:
        operation()
    except Exception:
        logger.exception("runtime bootstrap stage failed: %s", stage)
        if critical:
            st.session_state["_tenant_init_stage"] = stage
            raise
        _set_optional_failure(stage, True)
        return False
    _set_optional_failure(stage, False)
    return True


def _install_runtime_hardening(username: str) -> None:
    # Only the verified tenant context and learning isolation are allowed to block
    # authenticated data access. Provider, chart, bot and presentation upgrades
    # are feature layers; a failure there must degrade the feature, not expose or
    # hide the user's entire portfolio.
    st.session_state["_runtime_optional_failures"] = []

    _run_runtime_stage(
        "ai_tenant_tables",
        lambda: _invoke_runtime(
            "ai_tenant_hardening",
            "register_ai_tenant_tables",
        ),
        critical=False,
    )
    _run_runtime_stage(
        "tenant_scope",
        lambda: _invoke_runtime(
            "tenant_scope",
            "install_tenant_scope",
            username,
        ),
        critical=True,
    )

    optional_stages: tuple[tuple[str, str, str], ...] = (
        (
            "market_data_hardening",
            "market_data_hardening",
            "install_market_data_hardening",
        ),
        (
            "market_data_router",
            "market_data_router_v5",
            "install_market_data_router",
        ),
        (
            "financial_data_router",
            "financial_data_router_v5",
            "install_financial_data_router",
        ),
        (
            "reporting_policy",
            "ai_engine_core.reporting_policy_v5",
            "install_reporting_policy",
        ),
        (
            "performance_runtime",
            "performance_runtime_v7",
            "install_performance_runtime",
        ),
        (
            "analysis_context",
            "analysis_context_v7",
            "install_analysis_context",
        ),
        (
            "chart_performance",
            "chart_performance_v7",
            "install_chart_performance",
        ),
        (
            "external_signal_journal",
            "ai_engine_core.external_signal_journal_v5",
            "install_external_signal_journal",
        ),
        (
            "analytics_hardening",
            "analytics_hardening",
            "install_analytics_hardening",
        ),
        (
            "portfolio_metrics",
            "portfolio_metrics_v2",
            "install_portfolio_metrics_v2",
        ),
        (
            "analysis_routes",
            "analysis_routes_v5",
            "install_analysis_routes",
        ),
    )
    for stage, module_name, function_name in optional_stages:
        _run_runtime_stage(
            stage,
            lambda module_name=module_name, function_name=function_name: _invoke_runtime(
                module_name,
                function_name,
            ),
            critical=False,
        )

    # Learned weights are shared process state unless the tenant prefix is active,
    # so this stage remains security-critical even though other AI features degrade.
    _run_runtime_stage(
        "ai_learning_scope",
        lambda: _invoke_runtime(
            "ai_tenant_hardening",
            "install_ai_learning_scope",
        ),
        critical=True,
    )


def _initialize_user_space(username: str) -> bool:
    for attempt in range(3):
        try:
            _install_runtime_hardening(username)
            st.session_state.pop("_tenant_init_failed", None)
            st.session_state.pop("_tenant_init_stage", None)
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

    ok, db_error = _initialize_database()
    if not ok:
        st.error(
            "تعذر الاتصال بقاعدة البيانات. راجع DATABASE_URL في Secrets."
        )
        st.caption(
            "فشل الاتصال الحالي لن يُحفظ في الكاش؛ يمكن إعادة المحاولة دون "
            "إعادة تشغيل التطبيق بالكامل."
        )
        if st.button(
            "إعادة محاولة قاعدة البيانات",
            type="primary",
            use_container_width=True,
        ):
            _init_db_once.clear()
            st.rerun()
        logger.error("database unavailable: %s", db_error[:300])
        st.stop()

    try:
        from database_security_hardening import (
            install_database_security_hardening,
        )
        from database_write_hardening import (
            install_database_write_hardening,
        )

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
        stage = str(st.session_state.get("_tenant_init_stage") or "tenant_unknown")
        st.caption(
            "تم منع فتح البيانات احترازيًا. "
            f"أعد المحاولة بعد تحديث التطبيق. رمز التشخيص: {stage}"
        )
        if st.button(
            "إعادة المحاولة",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.pop("_tenant_init_failed", None)
            st.session_state.pop("_tenant_init_stage", None)
            st.rerun()
        st.stop()

    _render_authenticated_header()

    optional_failures = _runtime_failures()
    if optional_failures:
        st.warning(
            "تم تشغيل أصولي في الوضع الآمن. بيانات المستخدم معزولة، "
            "لكن بعض إضافات التحليل أو الربط متوقفة مؤقتًا."
        )
        st.caption("رموز المزايا المتأثرة: " + "، ".join(optional_failures))

    if st.session_state.get("_tenant_unclaimed_legacy"):
        st.warning(
            "توجد بيانات قديمة غير مرتبطة بمستخدم، ولم تُنسب تلقائيًا "
            "لأن قاعدة البيانات تحتوي أكثر من حساب. "
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
